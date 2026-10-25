"""Several Anthropic accounts as distinct, grant-metered providers.

The built-in ``anthropic`` provider keeps its behaviour; an extra account
(``anthropic-<suffix>``) is declared in the org config, uses the native
adapter, is fail-closed (registered only when listed in
``PROVIDER_GRANTS_REQUIRED_FOR``) and only ever spends under its own grant.

Every amount and date here is a generic placeholder.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio

from madfam_budget_gate.cost_model import estimate_cost
from madfam_inference import credentials
from madfam_inference import grants as g
from madfam_inference.base import InferenceProvider, UsageCallback
from madfam_inference.factory import build_router_from_env
from madfam_inference.org_config import OrgConfig, ProviderConfig, load_org_config
from madfam_inference.providers.anthropic import AnthropicProvider
from madfam_inference.router import ModelRouter
from madfam_inference.types import InferenceRequest, InferenceResponse, RoutingPolicy

NOW = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)
EXTRA = "anthropic-ops"
EXTRA_ENV = "ANTHROPIC_API_KEY_OPS"


def _grant(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "main-grant",
        "provider": "anthropic",
        "key_env": "ANTHROPIC_API_KEY",
        "amount_usd": 100.0,
        "safety_margin_usd": 5.0,
        "starts_at": "2030-01-01T00:00:00Z",
        "expires_at": "2030-01-02T00:00:00Z",
        "allowed_orgs": ["madfam"],
        "pacing": "steady",
        "autopilot": False,
    }
    base.update(overrides)
    return base


def _extra_grant(**overrides: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {"id": "ops-grant", "provider": EXTRA, "key_env": EXTRA_ENV}
    fields.update(overrides)
    return _grant(**fields)


def _state(*grants: dict[str, Any]) -> g.GrantConfigState:
    book = g.parse_grants(json.dumps({"grants": list(grants)}))
    return g.GrantConfigState(grants=tuple(book.grants), source="test")


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _guard(
    redis: Any,
    *grants: dict[str, Any],
    required: tuple[str, ...] = ("anthropic", EXTRA),
    now: datetime = NOW,
) -> g.GrantGuard:
    st = _state(*grants)
    return g.GrantGuard(
        config_loader=lambda: st,
        required=required,
        meter=g.GrantMeter(redis),
        platform_orgs={"madfam"},
        now_fn=lambda: now,
    )


def _req(org: str | None = "madfam", **policy: Any) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        policy=RoutingPolicy(max_tokens=1000, org_id=org, **policy),
    )


class _Provider(InferenceProvider):
    def __init__(self, name: str, credential_env: str | None = None) -> None:
        self.name = name
        self.credential_env = credential_env
        self.calls: list[str | None] = []

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request.policy.model_override)
        return InferenceResponse(
            content="ok",
            model=request.policy.model_override or "claude-sonnet-5-5",
            provider=self.name,
            usage={"input_tokens": 1000, "output_tokens": 500},
        )

    async def stream(
        self, request: InferenceRequest, on_usage: UsageCallback | None = None
    ) -> AsyncIterator[str]:
        yield "chunk"

    async def list_models(self) -> list[str]:
        return []


def _infra_policy() -> dict[str, Any]:
    """What a server-side infra-ops caller sets: prefer the extra account."""
    return {
        "provider_allowlist": [EXTRA, "anthropic"],
        "provider_models": {EXTRA: "claude-sonnet-5-5", "anthropic": "claude-sonnet-5-5"},
    }


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant(_s: float) -> None:
        return None

    monkeypatch.setattr("madfam_inference.router.asyncio.sleep", _instant)


# ── Naming ───────────────────────────────────────────────────────────────


class TestCredentialNames:
    def test_family(self) -> None:
        assert credentials.provider_family("anthropic") == "anthropic"
        assert credentials.provider_family(EXTRA) == "anthropic"
        assert credentials.provider_family("deepinfra") == "deepinfra"

    def test_extra(self) -> None:
        assert credentials.is_extra_credential(EXTRA)
        assert not credentials.is_extra_credential("anthropic")
        assert not credentials.is_extra_credential("deepinfra")

    def test_valid_names(self) -> None:
        assert credentials.valid_credential_name("anthropic-backup")
        assert not credentials.valid_credential_name("anthropic")
        assert not credentials.valid_credential_name("anthropic-")
        assert not credentials.valid_credential_name("anthropic-Ops")
        assert not credentials.valid_credential_name("claude-ops")


# ── Org config + factory ─────────────────────────────────────────────────


def _write_config(tmp_path: Path, providers: dict[str, Any]) -> str:
    import yaml

    path = tmp_path / "org-config.yaml"
    path.write_text(yaml.safe_dump({"providers": providers}))
    return str(path)


@pytest.fixture
def _fresh_config() -> Any:
    load_org_config.cache_clear()
    yield
    load_org_config.cache_clear()


class TestOrgConfigAdapter:
    def test_default_adapter_still_needs_base_url(self) -> None:
        with pytest.raises(ValueError):
            ProviderConfig(api_key_env="X")
        assert ProviderConfig(base_url="https://x.invalid/v1", api_key_env="X").adapter == (
            "openai_compatible"
        )

    def test_anthropic_adapter_needs_no_base_url(self) -> None:
        cfg = ProviderConfig(adapter="anthropic", api_key_env=EXTRA_ENV)
        assert cfg.base_url == ""


@pytest.mark.usefixtures("_fresh_config")
class TestFactory:
    def _build(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, required: str,
               key: str | None = "sk-extra-placeholder",
               entry: dict[str, Any] | None = None, name: str = EXTRA,
               main_key: str | None = None) -> ModelRouter:
        monkeypatch.setenv("PROVIDER_GRANTS_REQUIRED_FOR", required)
        if key is None:
            monkeypatch.delenv(EXTRA_ENV, raising=False)
        else:
            monkeypatch.setenv(EXTRA_ENV, key)
        cfg = entry if entry is not None else {"adapter": "anthropic", "api_key_env": EXTRA_ENV}
        return build_router_from_env(
            org_config_path=_write_config(tmp_path, {name: cfg}),
            anthropic_api_key=main_key,
        )

    def test_registers_native_adapter_with_its_own_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = self._build(tmp_path, monkeypatch, required=f"anthropic,{EXTRA}")
        provider = router._providers[EXTRA]
        assert isinstance(provider, AnthropicProvider)
        assert provider.name == EXTRA
        assert provider.credential_env == EXTRA_ENV

    def test_absent_key_is_not_registered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = self._build(tmp_path, monkeypatch, required=f"anthropic,{EXTRA}", key=None)
        assert EXTRA not in router.available_providers

    def test_not_in_required_for_is_not_registered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        router = self._build(tmp_path, monkeypatch, required="anthropic")
        assert EXTRA not in router.available_providers
        assert "PROVIDER_GRANTS_REQUIRED_FOR" in caplog.text

    def test_empty_required_for_is_not_registered(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = self._build(tmp_path, monkeypatch, required="")
        assert EXTRA not in router.available_providers

    def test_extra_name_on_openai_compatible_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry = {"base_url": "https://proxy.invalid/v1", "api_key_env": EXTRA_ENV}
        router = self._build(tmp_path, monkeypatch, required=EXTRA, entry=entry)
        assert EXTRA not in router.available_providers

    def test_anthropic_adapter_needs_the_family_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        router = self._build(tmp_path, monkeypatch, required="claude-ops", name="claude-ops")
        assert "claude-ops" not in router.available_providers

    def test_single_key_behaviour_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PROVIDER_GRANTS_REQUIRED_FOR", raising=False)
        router = build_router_from_env(
            org_config_path=str(tmp_path / "absent.yaml"), anthropic_api_key="sk-main"
        )
        provider = router._providers["anthropic"]
        assert isinstance(provider, AnthropicProvider)
        assert provider.name == "anthropic"
        assert provider.credential_env is None  # no key_env check on the built-in key
        assert sorted(router.available_providers) == ["anthropic", "ollama"]


# ── Guard: two accounts never cross grants ───────────────────────────────


class TestGuardSeparation:
    async def test_each_account_reserves_on_its_own_grant(self, redis: Any) -> None:
        guard = _guard(redis, _grant(), _extra_grant())
        main = await guard.reserve("anthropic", "madfam", None, _req())
        extra = await guard.reserve(EXTRA, "madfam", None, _req(), credential_env=EXTRA_ENV)
        assert main.allowed and main.grant_id == "main-grant"
        assert extra.allowed and extra.grant_id == "ops-grant"

    async def test_dead_main_grant_does_not_borrow_the_extra_one(self, redis: Any) -> None:
        expired_main = _grant(expires_at="2030-01-01T06:00:00Z")
        guard = _guard(redis, expired_main, _extra_grant())
        decision = await guard.reserve("anthropic", "madfam", None, _req())
        assert not decision.allowed and decision.reason == "expired"

    async def test_extra_account_without_grant_is_refused(self, redis: Any) -> None:
        guard = _guard(redis, _grant())  # only the main account has a grant
        decision = await guard.reserve(EXTRA, "madfam", None, _req(), credential_env=EXTRA_ENV)
        assert not decision.allowed and decision.reason == "no_grant"

    async def test_extra_account_not_required_is_refused(self, redis: Any) -> None:
        guard = _guard(redis, _grant(), _extra_grant(), required=("anthropic",))
        decision = await guard.reserve(EXTRA, "madfam", None, _req(), credential_env=EXTRA_ENV)
        assert not decision.allowed and decision.reason == "not_grant_required"

    async def test_extra_account_is_always_guarded(self, redis: Any) -> None:
        guard = _guard(redis, required=())
        assert guard.is_guarded(EXTRA)

    async def test_key_env_mismatch_is_refused(self, redis: Any) -> None:
        wrong = _extra_grant(key_env="ANTHROPIC_API_KEY")  # would meter the main account
        guard = _guard(redis, wrong)
        decision = await guard.reserve(EXTRA, "madfam", None, _req(), credential_env=EXTRA_ENV)
        assert not decision.allowed and decision.reason == "key_env_mismatch"

    async def test_grant_without_key_env_is_accepted(self, redis: Any) -> None:
        guard = _guard(redis, _extra_grant(key_env=None))
        decision = await guard.reserve(EXTRA, "madfam", None, _req(), credential_env=EXTRA_ENV)
        assert decision.allowed

    async def test_spend_lands_on_the_paying_account_only(self, redis: Any) -> None:
        guard = _guard(redis, _grant(), _extra_grant())
        extra = _Provider(EXTRA, EXTRA_ENV)
        main = _Provider("anthropic")
        router = ModelRouter(
            providers={"anthropic": main, EXTRA: extra}, org_config=OrgConfig(),
            grant_guard=guard,
        )
        resp = await router.complete(_req(**_infra_policy()))
        assert resp.provider == EXTRA and main.calls == []
        by_id = {s.id: s for s in await guard.statuses()}
        assert by_id["ops-grant"].spent_usd == pytest.approx(
            estimate_cost("anthropic", "claude-sonnet-5-5", 1000, 500)
        )
        assert by_id["main-grant"].spent_usd == 0.0


# ── Router: explicit routing only, fallback across accounts ──────────────


class TestRouting:
    def _router(self, guard: g.GrantGuard) -> tuple[ModelRouter, _Provider, _Provider, _Provider]:
        main, extra, deep = _Provider("anthropic"), _Provider(EXTRA, EXTRA_ENV), _Provider(
            "deepinfra"
        )
        org = OrgConfig(cloud_priority=["deepinfra", "anthropic"])
        router = ModelRouter(
            providers={"anthropic": main, EXTRA: extra, "deepinfra": deep},
            org_config=org,
            grant_guard=guard,
        )
        return router, main, extra, deep

    async def test_extra_account_is_not_in_default_routing(self, redis: Any) -> None:
        router, main, extra, deep = self._router(_guard(redis, _grant(), _extra_grant()))
        resp = await router.complete(_req())
        assert resp.provider == "deepinfra" and extra.calls == []

    async def test_other_tenant_never_reaches_extra_account(self, redis: Any) -> None:
        router, main, extra, deep = self._router(_guard(redis, _grant(), _extra_grant()))
        with pytest.raises(RuntimeError):
            await router.complete(_req(org="someone-else", **_infra_policy()))
        assert extra.calls == [] and main.calls == []

    async def test_infra_allowlist_prefers_extra_account(self, redis: Any) -> None:
        router, main, extra, _ = self._router(_guard(redis, _grant(), _extra_grant()))
        resp = await router.complete(_req(**_infra_policy()))
        assert resp.provider == EXTRA and extra.calls == ["claude-sonnet-5-5"]

    async def test_falls_back_to_main_when_extra_is_dead(self, redis: Any) -> None:
        expired_extra = _extra_grant(expires_at="2030-01-01T06:00:00Z")
        router, main, extra, _ = self._router(_guard(redis, _grant(), expired_extra))
        resp = await router.complete(_req(**_infra_policy()))
        assert resp.provider == "anthropic" and extra.calls == []

    async def test_no_funded_account_calls_no_key(self, redis: Any) -> None:
        later = NOW + timedelta(days=3)  # both grants expired
        router, main, extra, deep = self._router(
            _guard(redis, _grant(), _extra_grant(), now=later)
        )
        with pytest.raises(RuntimeError):
            await router.complete(_req(**_infra_policy()))
        assert main.calls == [] and extra.calls == [] and deep.calls == []

    async def test_extra_account_guarded_even_when_guard_is_inert(self) -> None:
        inert = g.GrantGuard(config_loader=lambda: g.GrantConfigState(), required=())
        assert not inert.enabled
        extra = _Provider(EXTRA, EXTRA_ENV)
        router = ModelRouter(providers={EXTRA: extra}, org_config=OrgConfig(),
                             grant_guard=inert)
        with pytest.raises(RuntimeError):
            await router.complete(_req(**_infra_policy()))
        assert extra.calls == []


def test_extra_account_priced_like_anthropic() -> None:
    assert estimate_cost(EXTRA, "claude-opus-5-5", 1000, 500) == estimate_cost(
        "anthropic", "claude-opus-5-5", 1000, 500
    )


def test_pinned_claude_model_counts_for_extra_account() -> None:
    assert g.is_pinned_to(EXTRA, "claude-opus-5-5")
    assert not g.is_pinned_to("deepinfra", "claude-opus-5-5")
