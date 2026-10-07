"""The pseudonymized-task exception, end to end through the gateway.

The vCTO client tenant keeps its ``restricted`` floor for everything except
ONE case: a ``family-feedback`` request that declares ``internal`` and
attests ``X-Pseudonymized: true`` may be drafted by Anthropic (primary) or
OpenAI (fallback) — and by no one else.

These tests drive the real proxy router and the real ``ModelRouter`` (with
recording providers in place of the vendors) and assert:

1. the exception path: Anthropic with its pinned model, OpenAI as fallback,
   the client's ``model`` ignored, the tenant's caps kept;
2. every way it must NOT apply — other task, missing or wrong attestation,
   ``restricted``/``confidential``/``public`` declared, other tenant, bad
   config, no policy loaded, providers outside the list — each one either
   served under the floor (local only) or refused, never by another cloud;
3. the gateway's identifier guard on excepted requests (400, nothing sent,
   nothing logged but the kind), and that it touches nothing else;
4. ``summarization`` and other tenants unchanged;
5. no prompt or completion persisted: the ledger gets tenant, task,
   provider, model, tokens and latency only.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI

from madfam_inference.base import InferenceProvider, UsageCallback
from madfam_inference.org_config import ModelAssignment, OrgConfig, TaskType
from madfam_inference.router import ModelRouter
from madfam_inference.tenant_policy import (
    TaskException,
    TenantPolicy,
    TenantPolicyBook,
    load_tenant_policies,
)
from madfam_inference.types import InferenceRequest, InferenceResponse, Sensitivity, StreamUsage
from nexus_api.auth import get_current_user
from nexus_api.database import get_db
from nexus_api.routers import inference_proxy

RESTRICTED_TENANT_ORG_ID = "e6cbd51d-8329-4c4e-8c74-aba643ab4575"
OTHER_TENANT_ORG_ID = "dhanam"
EXCEPTED_TASK = "family-feedback"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o"

# A pseudonymized draft request: placeholders where the names were.
PSEUDONYMIZED_TEXT = "[PERSONA_1] trabajó con atención en dos actividades durante la sesión."
DRAFT_TEXT = "Borrador sugerido para [PERSONA_1]."

EXCEPTION_HEADERS = {
    "Authorization": "Bearer t",
    "X-Sensitivity": "internal",
    "X-Task-Type": EXCEPTED_TASK,
    "X-Pseudonymized": "true",
}

CLOUD_OUTSIDE_THE_LIST = ("groq", "openrouter", "deepinfra", "mistral")


class RecordingProvider(InferenceProvider):
    """Stands in for a vendor; records the model it was asked for, at call time."""

    def __init__(self, provider_name: str, *, fail: bool = False, delay: float = 0.0) -> None:
        self.name = provider_name
        self.fail = fail
        self.delay = delay
        self.calls: list[str | None] = []

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request.policy.model_override)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError(f"{self.name} 503 service unavailable")
        return InferenceResponse(
            content=DRAFT_TEXT,
            model=request.policy.model_override or f"{self.name}-default",
            provider=self.name,
            usage={"input_tokens": 40, "output_tokens": 12},
        )

    async def stream(
        self, request: InferenceRequest, on_usage: UsageCallback | None = None
    ) -> AsyncIterator[str]:
        self.calls.append(request.policy.model_override)
        if self.fail:
            raise RuntimeError(f"{self.name} 503 service unavailable")
        yield DRAFT_TEXT
        if on_usage is not None:
            on_usage(
                StreamUsage(input_tokens=40, output_tokens=12, model=request.policy.model_override)
            )

    async def list_models(self) -> list[str]:
        return []


def _vendors(
    names: tuple[str, ...] = ("ollama", "anthropic", "openai", *CLOUD_OUTSIDE_THE_LIST),
    **behaviour: dict[str, Any],
) -> dict[str, RecordingProvider]:
    return {name: RecordingProvider(name, **behaviour.get(name, {})) for name in names}


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


def _exception(**overrides: Any) -> TaskException:
    fields: dict[str, Any] = {
        "sensitivity_floor": "internal",
        "allowed_providers": ["anthropic", "openai"],
        "requires_header": "X-Pseudonymized: true",
        "models": {"anthropic": ANTHROPIC_MODEL, "openai": OPENAI_MODEL},
        "authorized_on": "2026-10-07",
    }
    fields.update(overrides)
    return TaskException.model_validate(fields)


def _book(*, with_exception: bool = True, **tenant_overrides: Any) -> TenantPolicyBook:
    """The shipped tenant policy: restricted floor plus the one exception."""
    fields: dict[str, Any] = {
        "org_id": RESTRICTED_TENANT_ORG_ID,
        "display_name": "vCTO client (restricted)",
        "sensitivity_floor": Sensitivity.RESTRICTED,
        "allowed_task_types": ["summarization", EXCEPTED_TASK],
        "max_tokens_cap": 1500,
        "request_timeout_seconds": 40.0,
        "rate_limit_per_minute": 30,
        "daily_usd_budget": 2.0,
        "task_exceptions": {EXCEPTED_TASK: _exception()} if with_exception else {},
    }
    fields.update(tenant_overrides)
    return TenantPolicyBook(tenants={RESTRICTED_TENANT_ORG_ID: TenantPolicy(**fields)})


def _build_app(org_id: str = RESTRICTED_TENANT_ORG_ID) -> FastAPI:
    app = FastAPI()
    app.include_router(inference_proxy.router, prefix="/v1")

    async def _fake_user() -> dict[str, Any]:
        return {"sub": "service:worker", "roles": ["service"], "org_id": org_id}

    async def _fake_db():
        yield None

    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    return app


async def _post(
    headers: dict[str, str], *, org_id: str = RESTRICTED_TENANT_ORG_ID, **body_overrides: Any
) -> httpx.Response:
    body: dict[str, Any] = {
        "model": "auto",
        "messages": [
            {"role": "system", "content": "Eres asistente de redacción."},
            {"role": "user", "content": PSEUDONYMIZED_TEXT},
        ],
        **body_overrides,
    }
    transport = httpx.ASGITransport(app=_build_app(org_id))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/chat/completions", json=body, headers=headers)


def _policies(book: TenantPolicyBook):
    return patch.object(inference_proxy, "_get_tenant_policies", return_value=book)


def _router(vendors: dict[str, RecordingProvider], org_config: OrgConfig | None = None):
    model_router = ModelRouter(
        providers=vendors, org_config=org_config or _production_shaped_org_config()
    )
    return patch.object(inference_proxy, "_get_router", return_value=model_router)


def _with(headers: dict[str, str], **changes: str | None) -> dict[str, str]:
    merged = dict(headers)
    for key, value in changes.items():
        name = key.replace("_", "-")
        if value is None:
            merged.pop(name, None)
        else:
            merged[name] = value
    return merged


def _cloud_calls(vendors: dict[str, RecordingProvider]) -> dict[str, list[str | None]]:
    return {name: v.calls for name, v in vendors.items() if name != "ollama" and v.calls}


def _no_retry_backoff():
    """Skip the router's 1 s pause before retrying a failed primary."""
    return patch("madfam_inference.router.asyncio.sleep", new_callable=AsyncMock)


@pytest.fixture(autouse=True)
def _isolated():
    """No ledger, no event emitter, fresh rate limiter and policy cache."""
    load_tenant_policies.cache_clear()
    inference_proxy._rate_limiter = None
    with (
        patch.object(inference_proxy, "_record_usage", new=AsyncMock()),
        patch.object(inference_proxy, "_emit_proxy_event"),
    ):
        yield
    load_tenant_policies.cache_clear()
    inference_proxy._rate_limiter = None


# ---------------------------------------------------------------------------
# 1. The exception path
# ---------------------------------------------------------------------------


class TestExceptionPath:
    async def test_anthropic_drafts_with_its_pinned_model(self) -> None:
        vendors = _vendors()
        with _policies(_book()), _router(vendors):
            resp = await _post(EXCEPTION_HEADERS, max_tokens=32000)

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["model"] == ANTHROPIC_MODEL
        assert body["choices"][0]["message"]["content"] == DRAFT_TEXT
        assert vendors["anthropic"].calls == [ANTHROPIC_MODEL]
        assert _cloud_calls(vendors) == {"anthropic": [ANTHROPIC_MODEL]}
        assert vendors["ollama"].calls == []

    async def test_openai_is_the_fallback_with_its_own_model(self) -> None:
        vendors = _vendors(anthropic={"fail": True})
        with _policies(_book()), _router(vendors), _no_retry_backoff():
            resp = await _post(EXCEPTION_HEADERS)

        assert resp.status_code == 200, resp.text
        assert resp.json()["model"] == OPENAI_MODEL
        assert vendors["openai"].calls == [OPENAI_MODEL]
        for name in CLOUD_OUTSIDE_THE_LIST:
            assert vendors[name].calls == [], f"{name} must never be tried"

    @pytest.mark.parametrize("client_model", ["gpt-4o-mini", "meta-llama/Llama-3.3-70B-Instruct"])
    async def test_the_client_model_cannot_steer_the_call(self, client_model: str) -> None:
        vendors = _vendors()
        with _policies(_book()), _router(vendors):
            resp = await _post(EXCEPTION_HEADERS, model=client_model)
        assert resp.status_code == 200
        assert vendors["anthropic"].calls == [ANTHROPIC_MODEL]

    async def test_tenant_caps_still_apply(self) -> None:
        seen: list[InferenceRequest] = []
        vendors = _vendors()
        original = vendors["anthropic"].complete

        async def _capture(request: InferenceRequest) -> InferenceResponse:
            seen.append(request.model_copy(deep=True))
            return await original(request)

        vendors["anthropic"].complete = _capture  # type: ignore[method-assign]
        with _policies(_book()), _router(vendors):
            await _post(EXCEPTION_HEADERS, max_tokens=32000)

        policy = seen[-1].policy
        assert policy.sensitivity is Sensitivity.INTERNAL
        assert policy.max_tokens == 1500
        assert policy.task_type == EXCEPTED_TASK
        assert policy.provider_allowlist == ["anthropic", "openai"]

    async def test_streaming_takes_the_same_path(self) -> None:
        vendors = _vendors(anthropic={"fail": True})
        recorded = AsyncMock()
        with (
            _policies(_book()),
            _router(vendors),
            patch.object(inference_proxy, "_record_stream_usage", new=recorded),
        ):
            resp = await _post(EXCEPTION_HEADERS, stream=True)

        assert resp.status_code == 200
        assert DRAFT_TEXT in resp.text
        assert vendors["openai"].calls == [OPENAI_MODEL]
        assert _cloud_calls(vendors) == {"anthropic": [ANTHROPIC_MODEL], "openai": [OPENAI_MODEL]}
        captured = recorded.await_args.args[1]
        assert captured["provider"] == "openai"
        assert captured["task_type"] == EXCEPTED_TASK
        assert isinstance(captured["duration_ms"], int)


# ---------------------------------------------------------------------------
# 2. Every way it must NOT apply
# ---------------------------------------------------------------------------


class TestExceptionDoesNotApply:
    """Each request below is served as `restricted` — the local model only —
    and no cloud provider is ever contacted."""

    async def _assert_served_local(
        self,
        headers: dict[str, str],
        *,
        org_id: str = RESTRICTED_TENANT_ORG_ID,
        book: TenantPolicyBook | None = None,
    ) -> None:
        vendors = _vendors()
        seen: list[Sensitivity] = []
        original = vendors["ollama"].complete

        async def _capture(request: InferenceRequest) -> InferenceResponse:
            seen.append(request.policy.sensitivity)
            return await original(request)

        vendors["ollama"].complete = _capture  # type: ignore[method-assign]
        with _policies(book if book is not None else _book()), _router(vendors):
            resp = await _post(headers, org_id=org_id)

        assert resp.status_code == 200, resp.text
        assert seen == [Sensitivity.RESTRICTED]
        assert _cloud_calls(vendors) == {}, "no cloud provider may be contacted"

    async def test_other_task_type(self) -> None:
        await self._assert_served_local(_with(EXCEPTION_HEADERS, X_Task_Type="summarization"))

    async def test_no_task_type(self) -> None:
        await self._assert_served_local(_with(EXCEPTION_HEADERS, X_Task_Type=None))

    async def test_missing_attestation(self) -> None:
        await self._assert_served_local(_with(EXCEPTION_HEADERS, X_Pseudonymized=None))

    @pytest.mark.parametrize("value", ["false", "yes", "1", "truthy"])
    async def test_wrong_attestation(self, value: str) -> None:
        await self._assert_served_local(_with(EXCEPTION_HEADERS, X_Pseudonymized=value))

    @pytest.mark.parametrize("declared", ["restricted", "confidential"])
    async def test_stronger_declaration_is_never_lowered(self, declared: str) -> None:
        """Declaring more protection never opens the exception (and this
        tenant's floor then lifts `confidential` to `restricted`)."""
        await self._assert_served_local(_with(EXCEPTION_HEADERS, X_Sensitivity=declared))

    async def test_public_declaration_gets_the_floor(self) -> None:
        await self._assert_served_local(_with(EXCEPTION_HEADERS, X_Sensitivity="public"))

    async def test_other_tenant_sending_the_same_headers(self) -> None:
        """No exception for another tenant; and because it attested the
        pseudonymized path without one, it is served as restricted rather
        than routed to the whole internal set."""
        await self._assert_served_local(EXCEPTION_HEADERS, org_id=OTHER_TENANT_ORG_ID)

    async def test_no_policy_loaded_at_all(self) -> None:
        """A policy file that failed to load must not turn an attested
        `internal` request into ordinary internal traffic."""
        await self._assert_served_local(EXCEPTION_HEADERS, book=TenantPolicyBook())

    async def test_tenant_without_the_exception(self) -> None:
        await self._assert_served_local(EXCEPTION_HEADERS, book=_book(with_exception=False))

    async def test_bad_config_fails_closed_to_the_floor(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """An exception naming an unauthorized provider is dropped at load
        with an ERROR; the request then gets the floor."""
        import yaml

        path = tmp_path / "tenant-policies.yaml"
        exception = {
            "sensitivity_floor": "internal",
            "allowed_providers": ["anthropic", "gemini"],
            "requires_header": "X-Pseudonymized: true",
            "models": {"anthropic": ANTHROPIC_MODEL, "gemini": "gemini-pro"},
            "authorized_on": "2026-10-07",
        }
        path.write_text(
            yaml.safe_dump(
                {
                    "tenants": {
                        RESTRICTED_TENANT_ORG_ID: {
                            "sensitivity_floor": "restricted",
                            "allowed_task_types": ["summarization", EXCEPTED_TASK],
                            "task_exceptions": {EXCEPTED_TASK: exception},
                        }
                    }
                }
            )
        )
        with caplog.at_level(logging.ERROR, logger="madfam_inference.tenant_policy"):
            book = load_tenant_policies(path)
        assert any("NOT in force" in r.getMessage() for r in caplog.records)
        await self._assert_served_local(EXCEPTION_HEADERS, book=book)

    async def test_providers_outside_the_list_are_never_used(self) -> None:
        """Only unauthorized clouds (and the local model) are up: a 503 that
        names the authorized ones — not groq, openrouter, deepinfra, mistral,
        and not a silent switch to the local model either."""
        vendors = _vendors(("ollama", *CLOUD_OUTSIDE_THE_LIST))
        with _policies(_book()), _router(vendors):
            resp = await _post(EXCEPTION_HEADERS)

        assert resp.status_code == 503
        error = resp.json()["error"]
        assert error["code"] == "exception_providers_unavailable"
        assert "anthropic, openai" in error["message"]
        assert all(v.calls == [] for v in vendors.values())

    async def test_both_authorized_providers_down_is_a_503(self) -> None:
        vendors = _vendors(anthropic={"fail": True}, openai={"fail": True})
        with _policies(_book()), _router(vendors), _no_retry_backoff():
            resp = await _post(EXCEPTION_HEADERS)

        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "exception_providers_unavailable"
        for name in ("ollama", *CLOUD_OUTSIDE_THE_LIST):
            assert vendors[name].calls == [], f"{name} must never be tried"

    async def test_unlisted_task_type_is_still_rejected(self) -> None:
        vendors = _vendors()
        with _policies(_book()), _router(vendors):
            resp = await _post(_with(EXCEPTION_HEADERS, X_Task_Type="coding"))
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "task_type_not_allowed"
        assert all(v.calls == [] for v in vendors.values())


# ---------------------------------------------------------------------------
# 3. The identifier guard on excepted requests
# ---------------------------------------------------------------------------


# kind -> (synthetic identifier, label the refusal must use)
IDENTIFIERS = {
    "email": ("contacto.prueba@example.com", "an email address"),
    "phone": ("777 123 4567", "a phone number"),
    "curp": ("GODE561231HDFRRN09", "a CURP"),
    "rfc": ("GODE561231AB1", "an RFC"),
}


class TestIdentifierGuard:
    @pytest.mark.parametrize("kind", sorted(IDENTIFIERS))
    async def test_identifier_is_refused_before_any_provider(
        self, kind: str, caplog: pytest.LogCaptureFixture
    ) -> None:
        identifier, label = IDENTIFIERS[kind]
        vendors = _vendors()
        with (
            _policies(_book()),
            _router(vendors),
            caplog.at_level(logging.DEBUG),
        ):
            resp = await _post(
                EXCEPTION_HEADERS,
                messages=[{"role": "user", "content": f"{PSEUDONYMIZED_TEXT} Dato: {identifier}"}],
            )

        assert resp.status_code == 400
        error = resp.json()["error"]
        assert error["code"] == "direct_identifier_detected"
        assert label in error["message"]
        assert identifier not in resp.text, "the refusal must not echo the identifier"
        assert all(v.calls == [] for v in vendors.values()), "nothing may be sent"

        logged = " ".join(r.getMessage() for r in caplog.records)
        assert kind in logged
        assert identifier not in logged
        assert PSEUDONYMIZED_TEXT not in logged

    async def test_identifier_in_the_system_prompt_is_refused(self) -> None:
        vendors = _vendors()
        with _policies(_book()), _router(vendors):
            resp = await _post(
                EXCEPTION_HEADERS,
                messages=[
                    {"role": "system", "content": "Firma como contacto.prueba@example.com"},
                    {"role": "user", "content": PSEUDONYMIZED_TEXT},
                ],
            )
        assert resp.status_code == 400
        assert all(v.calls == [] for v in vendors.values())

    async def test_image_content_is_refused(self) -> None:
        vendors = _vendors()
        with _policies(_book()), _router(vendors):
            resp = await _post(
                EXCEPTION_HEADERS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": PSEUDONYMIZED_TEXT},
                            {"type": "image_url", "image_url": {"url": "https://x.example/a.png"}},
                        ],
                    }
                ],
            )
        assert resp.status_code == 400
        assert "non-text content" in resp.json()["error"]["message"]
        assert all(v.calls == [] for v in vendors.values())

    async def test_guard_applies_only_to_excepted_requests(self) -> None:
        """Local-only traffic is not refused for carrying an identifier: the
        floor already keeps it in the perimeter, exactly as before."""
        vendors = _vendors()
        with _policies(_book()), _router(vendors):
            resp = await _post(
                _with(EXCEPTION_HEADERS, X_Sensitivity="restricted", X_Task_Type="summarization"),
                messages=[{"role": "user", "content": "Llamar al 777 123 4567"}],
            )
        assert resp.status_code == 200
        assert vendors["ollama"].calls != []


# ---------------------------------------------------------------------------
# 4. Nothing else changes
# ---------------------------------------------------------------------------


class TestEverythingElseUnchanged:
    async def test_summarization_stays_local_only(self) -> None:
        vendors = _vendors()
        headers = {
            "Authorization": "Bearer t",
            "X-Sensitivity": "restricted",
            "X-Task-Type": "summarization",
        }
        with _policies(_book()), _router(vendors):
            resp = await _post(headers)
        assert resp.status_code == 200
        assert vendors["ollama"].calls == [None]
        assert _cloud_calls(vendors) == {}

    async def test_summarization_declared_internal_is_raised_to_the_floor(self) -> None:
        vendors = _vendors()
        headers = {
            "Authorization": "Bearer t",
            "X-Sensitivity": "internal",
            "X-Task-Type": "summarization",
        }
        with _policies(_book()), _router(vendors):
            resp = await _post(headers)
        assert resp.status_code == 200
        assert _cloud_calls(vendors) == {}

    async def test_other_tenant_internal_traffic_is_untouched(self) -> None:
        """Another tenant's ordinary `internal` call — even with the same task
        label and an email in it — routes exactly as before: org-config
        priority, no allowlist, no identifier guard."""
        vendors = _vendors()
        headers = {
            "Authorization": "Bearer t",
            "X-Sensitivity": "internal",
            "X-Task-Type": EXCEPTED_TASK,
        }
        with _policies(_book()), _router(vendors):
            resp = await _post(
                headers,
                org_id=OTHER_TENANT_ORG_ID,
                messages=[{"role": "user", "content": "Escribe a ana@example.com"}],
            )
        assert resp.status_code == 200
        assert _cloud_calls(vendors) == {"deepinfra": [None]}

    async def test_rate_limit_still_applies(self) -> None:
        vendors = _vendors()
        with _policies(_book(rate_limit_per_minute=2)), _router(vendors):
            first = await _post(EXCEPTION_HEADERS)
            second = await _post(EXCEPTION_HEADERS)
            third = await _post(EXCEPTION_HEADERS)
        assert [first.status_code, second.status_code, third.status_code] == [200, 200, 429]
        assert len(vendors["anthropic"].calls) == 2

    async def test_tenant_deadline_still_applies(self) -> None:
        vendors = _vendors(anthropic={"delay": 5.0})
        with _policies(_book(request_timeout_seconds=0.05)), _router(vendors):
            resp = await _post(EXCEPTION_HEADERS)
        assert resp.status_code == 504
        assert resp.json()["error"]["code"] == "inference_timeout"


# ---------------------------------------------------------------------------
# 5. Nothing persisted but metadata
# ---------------------------------------------------------------------------


class TestNoContentPersisted:
    async def test_ledger_gets_tenant_task_provider_model_tokens_latency_only(self) -> None:
        vendors = _vendors()
        recorded = AsyncMock()
        with (
            _policies(_book()),
            _router(vendors),
            patch.object(inference_proxy, "_record_usage", new=recorded),
        ):
            resp = await _post(EXCEPTION_HEADERS)

        assert resp.status_code == 200
        recorded.assert_awaited_once()
        args, kwargs = recorded.await_args.args, recorded.await_args.kwargs
        _db, user, provider, model, usage = args
        assert user["org_id"] == RESTRICTED_TENANT_ORG_ID
        assert (provider, model) == ("anthropic", ANTHROPIC_MODEL)
        assert usage == {"prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52}
        assert kwargs["task_type"] == EXCEPTED_TASK
        assert isinstance(kwargs["latency_ms"], int) and kwargs["latency_ms"] >= 0

        serialized = repr(args) + repr(kwargs)
        assert PSEUDONYMIZED_TEXT not in serialized
        assert DRAFT_TEXT not in serialized

    async def test_excepted_call_logs_no_content(self, caplog: pytest.LogCaptureFixture) -> None:
        vendors = _vendors(anthropic={"fail": True})
        with (
            _policies(_book()),
            _router(vendors),
            _no_retry_backoff(),
            caplog.at_level(logging.DEBUG),
        ):
            await _post(EXCEPTION_HEADERS)
        logged = " ".join(r.getMessage() for r in caplog.records)
        assert "pseudonymized-task exception applies" in logged
        assert PSEUDONYMIZED_TEXT not in logged
        assert DRAFT_TEXT not in logged

    def test_ledger_has_the_metadata_columns_and_still_no_content_column(self) -> None:
        from nexus_api.models import ComputeTokenLedger

        columns = {c.name for c in ComputeTokenLedger.__table__.columns}
        assert {"org_id", "task_type", "provider", "model", "amount", "cost_usd", "latency_ms"} <= (
            columns
        )
        assert not columns & {"prompt", "completion", "content", "messages", "response", "text"}
