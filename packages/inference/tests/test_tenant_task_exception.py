"""The pseudonymized-task exception: schema, loader, resolver and router.

One owner-authorized exception lets ONE task of ONE tenant reach a named list
of cloud providers instead of the tenant's ``restricted`` floor. These tests
pin down how narrow that is:

- the config is strict, and a broken exception fails CLOSED (the floor stays)
  without ever taking the tenant's floor down with it;
- the exception applies only when tenant, task type, declared ``internal``
  and the ``X-Pseudonymized: true`` attestation ALL hold;
- the provider set is the allowlist intersected with the router's
  ``internal`` set, in order, and nothing (org-config priority lists,
  model_assignments, prefer_local) can widen it;
- each provider gets its own pinned model, on fallback too.

The gateway-level behaviour (headers, identifier guard, ledger) is covered in
``apps/nexus-api/tests/test_inference_proxy_task_exception.py``.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from madfam_inference.base import InferenceProvider, UsageCallback
from madfam_inference.org_config import ModelAssignment, OrgConfig, TaskType
from madfam_inference.router import CLOUD_PRIORITY, ModelRouter
from madfam_inference.tenant_policy import (
    PSEUDONYMIZATION_REQUIREMENT,
    TaskException,
    TenantPolicy,
    TenantPolicyBook,
    load_tenant_policies,
    pseudonymization_attested,
    pseudonymization_header_sent,
    resolve_task_exception,
)
from madfam_inference.types import (
    InferenceRequest,
    InferenceResponse,
    RoutingPolicy,
    Sensitivity,
    StreamUsage,
)

RESTRICTED_TENANT_ORG_ID = "e6cbd51d-8329-4c4e-8c74-aba643ab4575"
EXCEPTED_TASK = "family-feedback"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o"


def _exception_fields(**overrides: Any) -> dict[str, Any]:
    """The shipped exception, as raw config, with per-test overrides."""
    fields: dict[str, Any] = {
        "sensitivity_floor": "internal",
        "allowed_providers": ["anthropic", "openai"],
        "requires_header": "X-Pseudonymized: true",
        "models": {"anthropic": ANTHROPIC_MODEL, "openai": OPENAI_MODEL},
        "authorized_on": "2026-10-07",
    }
    fields.update(overrides)
    return fields


def _tenant(**exception_overrides: Any) -> TenantPolicy:
    return TenantPolicy(
        org_id=RESTRICTED_TENANT_ORG_ID,
        sensitivity_floor=Sensitivity.RESTRICTED,
        allowed_task_types=["summarization", EXCEPTED_TASK],
        task_exceptions={
            EXCEPTED_TASK: TaskException.model_validate(_exception_fields(**exception_overrides))
        },
    )


@pytest.fixture(autouse=True)
def _clear_policy_cache():
    load_tenant_policies.cache_clear()
    yield
    load_tenant_policies.cache_clear()


# ---------------------------------------------------------------------------
# 1. The schema is strict
# ---------------------------------------------------------------------------


class TestTaskExceptionSchema:
    def test_the_shipped_shape_is_valid(self) -> None:
        exception = TaskException.model_validate(_exception_fields())
        assert exception.sensitivity_floor is Sensitivity.INTERNAL
        assert exception.allowed_providers == ["anthropic", "openai"]
        assert exception.requires_header == PSEUDONYMIZATION_REQUIREMENT
        assert exception.models == {"anthropic": ANTHROPIC_MODEL, "openai": OPENAI_MODEL}
        assert exception.authorized_on == date(2026, 10, 7)

    @pytest.mark.parametrize("level", ["public", "confidential", "restricted"])
    def test_only_internal_is_accepted(self, level: str) -> None:
        """`public` would reach the cheapest-vendor list; `restricted` or
        `confidential` would be a no-op that reads like an exception."""
        with pytest.raises(ValidationError, match="internal"):
            TaskException.model_validate(_exception_fields(sensitivity_floor=level))

    @pytest.mark.parametrize(
        "providers",
        [
            [],
            ["anthropic", "anthropic"],
            ["anthropic", " "],
            ["anthropic", "ollama"],  # local is not a cloud exception
            ["anthropic", "gemini"],  # not a provider this router knows
            ["anthropic", "openia"],  # a typo fails loudly, not silently narrower
        ],
    )
    def test_providers_must_be_known_internal_providers(self, providers: list[str]) -> None:
        models = {name: "m" for name in providers if name.strip()}
        with pytest.raises(ValidationError):
            TaskException.model_validate(
                _exception_fields(allowed_providers=providers, models=models)
            )

    @pytest.mark.parametrize(
        "header",
        [
            "X-Pseudonymized: yes",
            "X-Pseudonymized: 1",
            "X-Pseudonymised: true",
            "Content-Type: application/json",
            "true",
            "",
        ],
    )
    def test_the_attestation_header_is_fixed(self, header: str) -> None:
        """The attestation cannot be swapped for a header every client sends."""
        with pytest.raises(ValidationError, match="requires_header"):
            TaskException.model_validate(_exception_fields(requires_header=header))

    @pytest.mark.parametrize(
        "header", ["x-pseudonymized: TRUE", "X-Pseudonymized:true", " X-Pseudonymized :  true "]
    )
    def test_header_spelling_is_normalised(self, header: str) -> None:
        exception = TaskException.model_validate(_exception_fields(requires_header=header))
        assert exception.requires_header == PSEUDONYMIZATION_REQUIREMENT

    def test_every_provider_needs_a_pinned_model(self) -> None:
        with pytest.raises(ValidationError, match="missing"):
            TaskException.model_validate(_exception_fields(models={"anthropic": ANTHROPIC_MODEL}))

    def test_models_cannot_name_another_provider(self) -> None:
        models = {"anthropic": ANTHROPIC_MODEL, "openai": OPENAI_MODEL, "groq": "llama"}
        with pytest.raises(ValidationError, match="outside allowed_providers"):
            TaskException.model_validate(_exception_fields(models=models))

    def test_blank_model_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="blank"):
            TaskException.model_validate(
                _exception_fields(models={"anthropic": " ", "openai": OPENAI_MODEL})
            )

    def test_unknown_keys_are_rejected(self) -> None:
        """A typo such as `allowed_provider:` must not silently default."""
        fields = _exception_fields()
        fields["allowed_provider"] = fields.pop("allowed_providers")
        with pytest.raises(ValidationError):
            TaskException.model_validate(fields)

    def test_the_decision_date_is_required(self) -> None:
        fields = _exception_fields()
        del fields["authorized_on"]
        with pytest.raises(ValidationError, match="authorized_on"):
            TaskException.model_validate(fields)


# ---------------------------------------------------------------------------
# 2. Loading fails CLOSED, per exception, and loudly
# ---------------------------------------------------------------------------


_ABSENT = object()


def _write_book(tmp_path: Path, task_exceptions: Any = _ABSENT) -> Path:
    """Write a one-tenant policy file, the way the ConfigMap ships it."""
    import yaml

    tenant: dict[str, Any] = {
        "sensitivity_floor": "restricted",
        "allowed_task_types": ["summarization", EXCEPTED_TASK],
        "max_tokens_cap": 1500,
    }
    if task_exceptions is not _ABSENT:
        tenant["task_exceptions"] = task_exceptions
    path = tmp_path / "tenant-policies.yaml"
    path.write_text(yaml.safe_dump({"tenants": {RESTRICTED_TENANT_ORG_ID: tenant}}))
    load_tenant_policies.cache_clear()
    return path


def _floor_intact(book: TenantPolicyBook) -> TenantPolicy:
    policy = book.for_org(RESTRICTED_TENANT_ORG_ID)
    assert policy is not None, "a bad exception must never drop the tenant"
    assert policy.sensitivity_floor is Sensitivity.RESTRICTED
    assert policy.max_tokens_cap == 1500
    return policy


class TestLoaderFailsClosed:
    def test_valid_exception_is_loaded_and_announced(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write_book(tmp_path, {EXCEPTED_TASK: _exception_fields()})
        with caplog.at_level(logging.INFO, logger="madfam_inference.tenant_policy"):
            book = load_tenant_policies(path)

        policy = _floor_intact(book)
        assert list(policy.task_exceptions) == [EXCEPTED_TASK]
        in_force = [r.getMessage() for r in caplog.records if "in force" in r.getMessage()]
        assert len(in_force) == 1
        assert EXCEPTED_TASK in in_force[0]
        assert "anthropic, openai" in in_force[0]
        assert "2026-10-07" in in_force[0]

    @pytest.mark.parametrize(
        "override",
        [
            {"allowed_providers": ["anthropic", "gemini"]},
            {"allowed_providers": "anthropic"},
            {"requires_header": "X-Pseudonymized: yes"},
            {"sensitivity_floor": "public"},
            {"models": {"anthropic": ANTHROPIC_MODEL}},
            {"surprise_key": 1},
        ],
    )
    def test_invalid_exception_is_dropped_but_the_floor_stays(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, override: dict[str, Any]
    ) -> None:
        path = _write_book(tmp_path, {EXCEPTED_TASK: _exception_fields(**override)})
        with caplog.at_level(logging.ERROR, logger="madfam_inference.tenant_policy"):
            book = load_tenant_policies(path)

        assert _floor_intact(book).task_exceptions == {}
        errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
        assert len(errors) == 1
        assert "NOT in force" in errors[0]
        assert EXCEPTED_TASK in errors[0]
        assert RESTRICTED_TENANT_ORG_ID in errors[0]

    @pytest.mark.parametrize("block", [[EXCEPTED_TASK], "family-feedback", 3])
    def test_a_block_that_is_not_a_mapping_is_ignored_loudly(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, block: Any
    ) -> None:
        path = _write_book(tmp_path, block)
        with caplog.at_level(logging.ERROR, logger="madfam_inference.tenant_policy"):
            book = load_tenant_policies(path)
        assert _floor_intact(book).task_exceptions == {}
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    @pytest.mark.parametrize("entry", [True, "yes", None, ["anthropic"]])
    def test_an_entry_that_is_not_a_mapping_is_ignored_loudly(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture, entry: Any
    ) -> None:
        path = _write_book(tmp_path, {EXCEPTED_TASK: entry})
        with caplog.at_level(logging.ERROR, logger="madfam_inference.tenant_policy"):
            book = load_tenant_policies(path)
        assert _floor_intact(book).task_exceptions == {}
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_an_exception_for_a_task_the_tenant_may_not_send_is_dropped(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = _write_book(tmp_path, {"coding": _exception_fields()})
        with caplog.at_level(logging.ERROR, logger="madfam_inference.tenant_policy"):
            book = load_tenant_policies(path)
        assert _floor_intact(book).task_exceptions == {}
        assert any("allowed_task_types" in r.getMessage() for r in caplog.records)

    def test_one_bad_exception_does_not_drop_a_good_one(self, tmp_path: Path) -> None:
        path = _write_book(
            tmp_path,
            {
                EXCEPTED_TASK: _exception_fields(),
                "summarization": _exception_fields(
                    allowed_providers=["deepseek"], models={"deepseek": "x"}
                ),
            },
        )
        book = load_tenant_policies(path)
        assert list(_floor_intact(book).task_exceptions) == [EXCEPTED_TASK]

    def test_absent_block_means_no_exception(self, tmp_path: Path) -> None:
        book = load_tenant_policies(_write_book(tmp_path))
        assert _floor_intact(book).task_exceptions == {}

    def test_shipped_production_file_declares_exactly_this_exception(self, tmp_path: Path) -> None:
        """Drift check on the manifest that actually ships, through the real
        loader: one exception, for family-feedback only, anthropic then
        openai, the floor untouched, nothing for summarization."""
        import yaml

        repo_root = Path(__file__).resolve().parents[3]
        manifest = repo_root / "infra" / "k8s" / "production" / "tenant-policies.yaml"
        embedded = yaml.safe_load(manifest.read_text())["data"]["tenant-policies.yaml"]
        path = tmp_path / "tenant-policies.yaml"
        path.write_text(embedded)

        book = load_tenant_policies(path)
        policy = _floor_intact(book)
        assert policy.allowed_task_types == ["summarization", EXCEPTED_TASK]
        assert set(policy.task_exceptions) == {EXCEPTED_TASK}
        exception = policy.task_exceptions[EXCEPTED_TASK]
        assert exception.sensitivity_floor is Sensitivity.INTERNAL
        assert exception.allowed_providers == ["anthropic", "openai"]
        assert exception.models == {"anthropic": ANTHROPIC_MODEL, "openai": OPENAI_MODEL}
        assert exception.requires_header == PSEUDONYMIZATION_REQUIREMENT
        assert exception.authorized_on == date(2026, 10, 7)
        # No other tenant carries an exception.
        assert [
            org
            for org, other in book.tenants.items()
            if other.task_exceptions and org != RESTRICTED_TENANT_ORG_ID
        ] == []


# ---------------------------------------------------------------------------
# 3. It applies only when EVERY condition holds
# ---------------------------------------------------------------------------


class TestResolveTaskException:
    def _resolve(self, policy: TenantPolicy | None = None, **kwargs: Any) -> TaskException | None:
        args: dict[str, Any] = {
            "task_type": EXCEPTED_TASK,
            "declared": Sensitivity.INTERNAL,
            "pseudonymized": "true",
        }
        args.update(kwargs)
        return resolve_task_exception(policy if policy is not None else _tenant(), **args)

    def test_all_conditions_hold(self) -> None:
        exception = self._resolve()
        assert exception is not None
        assert exception.allowed_providers == ["anthropic", "openai"]

    @pytest.mark.parametrize("value", ["true", "TRUE", " True ", "true\n"])
    def test_attestation_spelling_is_tolerated(self, value: str) -> None:
        assert self._resolve(pseudonymized=value) is not None

    @pytest.mark.parametrize("value", [None, "", "false", "yes", "1", "truee", "true, false"])
    def test_without_the_attestation_it_does_not_apply(self, value: str | None) -> None:
        assert self._resolve(pseudonymized=value) is None

    @pytest.mark.parametrize("task_type", ["summarization", "coding", "Family-Feedback", "", None])
    def test_other_task_types_do_not_get_it(self, task_type: str | None) -> None:
        assert self._resolve(task_type=task_type) is None

    @pytest.mark.parametrize(
        "declared", [Sensitivity.PUBLIC, Sensitivity.CONFIDENTIAL, Sensitivity.RESTRICTED]
    )
    def test_only_a_declared_internal_request_gets_it(self, declared: Sensitivity) -> None:
        """Over-declaring keeps the stronger level; under-declaring `public`
        is not an attestation of anything either."""
        assert self._resolve(declared=declared) is None

    def test_a_tenant_without_the_exception_does_not_get_it(self) -> None:
        other = TenantPolicy(org_id="dhanam")
        assert (
            resolve_task_exception(
                other, task_type=EXCEPTED_TASK, declared=Sensitivity.INTERNAL, pseudonymized="true"
            )
            is None
        )

    def test_no_policy_means_no_exception(self) -> None:
        assert (
            resolve_task_exception(
                None, task_type=EXCEPTED_TASK, declared=Sensitivity.INTERNAL, pseudonymized="true"
            )
            is None
        )

    def test_header_helpers(self) -> None:
        assert pseudonymization_attested("true") is True
        assert pseudonymization_attested("false") is False
        assert pseudonymization_header_sent("false") is True
        assert pseudonymization_header_sent("  ") is False
        assert pseudonymization_header_sent(None) is False


# ---------------------------------------------------------------------------
# 4. The router: allowlist ∩ internal set, in order, models pinned
# ---------------------------------------------------------------------------


class RecordingProvider(InferenceProvider):
    """Records the model it was asked for AT CALL TIME (the policy object is
    shared and mutated between attempts, so a later read would lie)."""

    def __init__(self, provider_name: str, *, fail: bool = False) -> None:
        self.name = provider_name
        self.fail = fail
        self.calls: list[str | None] = []

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request.policy.model_override)
        if self.fail:
            raise RuntimeError(f"{self.name} 503 service unavailable")
        return InferenceResponse(
            content="borrador",
            model=request.policy.model_override or f"{self.name}-default",
            provider=self.name,
            usage={"input_tokens": 10, "output_tokens": 5},
        )

    async def stream(
        self, request: InferenceRequest, on_usage: UsageCallback | None = None
    ) -> AsyncIterator[str]:
        self.calls.append(request.policy.model_override)
        if self.fail:
            raise RuntimeError(f"{self.name} 503 service unavailable")
        yield "borrador"
        if on_usage is not None:
            on_usage(
                StreamUsage(input_tokens=10, output_tokens=5, model=request.policy.model_override)
            )

    async def list_models(self) -> list[str]:
        return []


def _providers(*names: str, failing: tuple[str, ...] = ()) -> dict[str, RecordingProvider]:
    return {name: RecordingProvider(name, fail=name in failing) for name in names}


ALL = ("ollama", "anthropic", "openai", "groq", "openrouter", "deepinfra", "mistral")


def _excepted_request(**policy_overrides: Any) -> InferenceRequest:
    fields: dict[str, Any] = {
        "sensitivity": Sensitivity.INTERNAL,
        "task_type": EXCEPTED_TASK,
        "max_tokens": 1500,
        "provider_allowlist": ["anthropic", "openai"],
        "provider_models": {"anthropic": ANTHROPIC_MODEL, "openai": OPENAI_MODEL},
    }
    fields.update(policy_overrides)
    return InferenceRequest(
        messages=[{"role": "user", "content": "texto seudonimizado"}],
        policy=RoutingPolicy(**fields),
    )


def _production_shaped_org_config() -> OrgConfig:
    """Production pins cloud_priority and every task type to DeepInfra."""
    return OrgConfig(
        model_assignments={
            task: ModelAssignment(provider="deepinfra", model="llama", max_tokens=8192)
            for task in TaskType
        },
        cloud_priority=["deepinfra"],
        cheapest_priority=["deepinfra"],
    )


class TestRouterUnderAnException:
    async def test_anthropic_is_primary_with_its_pinned_model(self) -> None:
        providers = _providers(*ALL)
        router = ModelRouter(providers=providers)
        response = await router.complete(_excepted_request())
        assert response.provider == "anthropic"
        assert providers["anthropic"].calls == [ANTHROPIC_MODEL]
        assert response.model == ANTHROPIC_MODEL

    async def test_openai_is_the_fallback_with_its_own_model(self) -> None:
        """The fallback must not be sent Anthropic's model id."""
        providers = _providers(*ALL, failing=("anthropic",))
        router = ModelRouter(providers=providers)
        response = await router.complete(_excepted_request())
        assert response.provider == "openai"
        assert providers["openai"].calls == [OPENAI_MODEL]
        assert providers["anthropic"].calls == [ANTHROPIC_MODEL, ANTHROPIC_MODEL]  # + retry

    async def test_without_anthropic_registered_openai_serves(self) -> None:
        providers = _providers("openai", "groq", "deepinfra")
        router = ModelRouter(providers=providers)
        response = await router.complete(_excepted_request())
        assert response.provider == "openai"
        assert providers["openai"].calls == [OPENAI_MODEL]

    async def test_no_provider_outside_the_list_is_ever_used(self) -> None:
        """Only providers outside the list are registered: the router raises
        rather than serve from groq, openrouter, deepinfra or the local one."""
        providers = _providers("ollama", "groq", "openrouter", "deepinfra", "mistral")
        router = ModelRouter(providers=providers)
        with pytest.raises(RuntimeError, match="No available provider"):
            await router.complete(_excepted_request())
        assert all(p.calls == [] for p in providers.values())

    async def test_both_listed_providers_down_is_an_error_not_a_wider_chain(self) -> None:
        providers = _providers(*ALL, failing=("anthropic", "openai"))
        router = ModelRouter(providers=providers)
        with pytest.raises(RuntimeError, match="All providers failed"):
            await router.complete(_excepted_request())
        for name in ("ollama", "groq", "openrouter", "deepinfra", "mistral"):
            assert providers[name].calls == [], f"{name} must never be tried"

    def test_allowed_set_is_the_intersection_with_the_internal_set(self) -> None:
        router = ModelRouter(providers=_providers(*ALL))
        request = _excepted_request(
            provider_allowlist=["ollama", "made-up", "anthropic", "anthropic"]
        )
        assert router.allowed_providers_for(request) == ["anthropic"]
        assert set(router.allowed_providers_for(_excepted_request())) <= set(CLOUD_PRIORITY)

    def test_org_priority_lists_neither_widen_nor_empty_it(self) -> None:
        """Deliberate: the exception is intersected with the router's
        internal set, not with org-config `cloud_priority` (a cost list that
        production pins to DeepInfra)."""
        router = ModelRouter(providers=_providers(*ALL), org_config=_production_shaped_org_config())
        assert router.allowed_providers_for(_excepted_request()) == ["anthropic", "openai"]
        # ...while a plain internal request keeps the org-config list.
        plain = InferenceRequest(
            messages=[{"role": "user", "content": "x"}],
            policy=RoutingPolicy(sensitivity=Sensitivity.INTERNAL),
        )
        assert router.allowed_providers_for(plain) == ["deepinfra"]

    @pytest.mark.parametrize("assigned", ["deepinfra", "groq", "openai"])
    async def test_model_assignments_are_not_consulted(self, assigned: str) -> None:
        """Not even an assignment INSIDE the set may swap the model or raise
        the token cap: the exception pins both."""
        org_config = OrgConfig(
            model_assignments={
                TaskType.RESEARCH: ModelAssignment(
                    provider=assigned, model="assigned-model", max_tokens=8192, temperature=0.1
                )
            }
        )
        providers = _providers(*ALL)
        router = ModelRouter(providers=providers, org_config=org_config)
        request = _excepted_request(task_type="research")
        response = await router.complete(request)
        assert response.provider == "anthropic"
        assert providers["anthropic"].calls == [ANTHROPIC_MODEL]
        assert request.policy.max_tokens == 1500

    def test_prefer_local_does_not_add_the_local_provider(self) -> None:
        router = ModelRouter(providers=_providers(*ALL))
        request = _excepted_request(prefer_local=True)
        assert router.allowed_providers_for(request) == ["anthropic", "openai"]

    @pytest.mark.parametrize("level", [Sensitivity.RESTRICTED, Sensitivity.CONFIDENTIAL])
    async def test_an_allowlist_never_lifts_a_local_only_level(self, level: Sensitivity) -> None:
        providers = _providers(*ALL)
        router = ModelRouter(providers=providers)
        request = _excepted_request(sensitivity=level)
        assert router.allowed_providers_for(request) == ["ollama"]
        response = await router.complete(request)
        assert response.provider == "ollama"
        assert providers["ollama"].calls == [None]  # no cloud model pinned onto it

    def test_require_local_wins_over_an_allowlist(self) -> None:
        router = ModelRouter(providers=_providers(*ALL))
        assert router.allowed_providers_for(_excepted_request(require_local=True)) == ["ollama"]

    async def test_an_empty_allowlist_means_no_provider(self) -> None:
        router = ModelRouter(providers=_providers(*ALL))
        with pytest.raises(RuntimeError, match="No available provider"):
            await router.complete(_excepted_request(provider_allowlist=[]))

    async def test_client_model_is_replaced_by_the_pinned_one(self) -> None:
        providers = _providers(*ALL)
        router = ModelRouter(providers=providers)
        await router.complete(_excepted_request(model_override="gpt-4o-mini"))
        assert providers["anthropic"].calls == [ANTHROPIC_MODEL]

    async def test_streaming_fallback_pins_the_fallback_model(self) -> None:
        providers = _providers(*ALL, failing=("anthropic",))
        router = ModelRouter(providers=providers)
        seen: list[StreamUsage] = []
        chunks = [c async for c in router.stream(_excepted_request(), on_usage=seen.append)]
        assert chunks == ["borrador"]
        assert providers["openai"].calls == [OPENAI_MODEL]
        assert seen and seen[-1].provider == "openai"

    async def test_requests_without_an_allowlist_route_as_before(self) -> None:
        """No other request is affected: no allowlist, no pinning, the usual
        internal order."""
        providers = _providers(*ALL)
        router = ModelRouter(providers=providers)
        request = InferenceRequest(
            messages=[{"role": "user", "content": "x"}],
            policy=RoutingPolicy(sensitivity=Sensitivity.INTERNAL, model_override="client-model"),
        )
        response = await router.complete(request)
        assert response.provider == CLOUD_PRIORITY[0]
        assert providers[CLOUD_PRIORITY[0]].calls == ["client-model"]
