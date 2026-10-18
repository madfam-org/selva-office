"""Provider credit grants: loader, fail-closed guard, Redis pacer, router hook.

Every amount and date here is a generic placeholder (contract C1 examples).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio

from madfam_budget_gate.cost_model import estimate_cost
from madfam_inference import grants as g
from madfam_inference.base import InferenceProvider, UsageCallback
from madfam_inference.org_config import ModelAssignment, OrgConfig, TaskType
from madfam_inference.router import ModelRouter
from madfam_inference.types import (
    InferenceRequest,
    InferenceResponse,
    RoutingPolicy,
    Sensitivity,
    StreamUsage,
)

NOW = datetime(2030, 1, 1, 12, 0, 0, tzinfo=UTC)


def _grant_dict(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "example-grant",
        "provider": "anthropic",
        "key_env": "ANTHROPIC_API_KEY",
        "amount_usd": 100.0,
        "safety_margin_usd": 5.0,
        "starts_at": "2030-01-01T00:00:00Z",
        "expires_at": "2030-01-02T00:00:00Z",
        "allowed_orgs": ["madfam"],
        "pacing": "use_it_or_lose_it",
        "autopilot": False,
        "notes": "placeholder",
    }
    base.update(overrides)
    return base


def _state(*grants: dict[str, Any]) -> g.GrantConfigState:
    book = g.parse_grants(json.dumps({"grants": list(grants)}))
    return g.GrantConfigState(grants=tuple(book.grants), source="test")


class _Clock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


def _guard(
    redis: Any,
    *grants: dict[str, Any],
    required: tuple[str, ...] = ("anthropic",),
    clock: _Clock | None = None,
    state: g.GrantConfigState | None = None,
    seeder: g.LedgerSeeder | None = None,
    ttl: int = 150,
) -> g.GrantGuard:
    st = state if state is not None else _state(*grants)
    meter = g.GrantMeter(redis, seeder=seeder, reservation_ttl_seconds=ttl) if redis else None
    return g.GrantGuard(
        config_loader=lambda: st,
        required=required,
        meter=meter,
        platform_orgs={"madfam"},
        now_fn=clock or _Clock(),
    )


def _req(max_tokens: int = 1000, org: str | None = "madfam", **policy: Any) -> InferenceRequest:
    return InferenceRequest(
        messages=[{"role": "user", "content": "hello"}],
        policy=RoutingPolicy(max_tokens=max_tokens, org_id=org, **policy),
    )


# ── Loader ───────────────────────────────────────────────────────────────


class TestLoader:
    def test_valid_json(self) -> None:
        book = g.parse_grants(json.dumps({"grants": [_grant_dict()]}))
        assert book.grants[0].ceiling_usd == 95.0
        assert book.grants[0].starts_at.tzinfo is not None

    def test_valid_yaml(self) -> None:
        text = (
            "grants:\n"
            "  - id: example-grant\n"
            "    provider: anthropic\n"
            "    amount_usd: 100\n"
            "    starts_at: '2030-01-01T00:00:00Z'\n"
            "    expires_at: '2030-01-02T00:00:00Z'\n"
            "    allowed_orgs: [madfam]\n"
        )
        assert g.parse_grants(text).grants[0].id == "example-grant"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"unknown_field": 1},
            {"starts_at": "2030-01-01T00:00:00"},  # naive timestamp
            {"expires_at": "2029-12-31T00:00:00Z"},  # before start
            {"safety_margin_usd": 100.0},
            {"amount_usd": 0},
            {"allowed_orgs": []},
            {"allowed_orgs": [" "]},
            {"provider": "Anthropic"},
            {"pacing": "yolo"},
            {"key_env": "lower-case"},
        ],
    )
    def test_rejects_invalid(self, overrides: dict[str, Any]) -> None:
        with pytest.raises(g.GrantConfigError):
            g.parse_grants(json.dumps({"grants": [_grant_dict(**overrides)]}))

    def test_rejects_duplicate_ids(self) -> None:
        with pytest.raises(g.GrantConfigError):
            g.parse_grants(json.dumps({"grants": [_grant_dict(), _grant_dict()]}))

    def test_rejects_garbage_and_wrong_top_level(self) -> None:
        with pytest.raises(g.GrantConfigError):
            g.parse_grants("{not: [valid")
        with pytest.raises(g.GrantConfigError):
            g.parse_grants("[1, 2]")

    def test_error_message_does_not_echo_values(self) -> None:
        with pytest.raises(g.GrantConfigError) as info:
            g.parse_grants(json.dumps({"grants": [_grant_dict(amount_usd=-1234.5)]}))
        assert "1234" not in str(info.value)

    def test_file_then_env_precedence(self, tmp_path: Path) -> None:
        f = tmp_path / "provider-grants.json"
        f.write_text(json.dumps({"grants": [_grant_dict(id="from-file")]}))
        env = {
            g.ENV_PATH: str(f),
            g.ENV_JSON: json.dumps({"grants": [_grant_dict(id="from-env")]}),
        }
        assert g.load_grant_config(env).grants[0].id == "from-file"

    def test_missing_file_falls_back_to_env_then_none(self, tmp_path: Path) -> None:
        missing = str(tmp_path / "absent.json")
        env = {g.ENV_PATH: missing, g.ENV_JSON: json.dumps({"grants": [_grant_dict()]})}
        assert g.load_grant_config(env).grants[0].id == "example-grant"
        st = g.load_grant_config({g.ENV_PATH: missing})
        assert st.grants == () and st.error is None

    def test_invalid_file_is_an_error_state(self, tmp_path: Path) -> None:
        f = tmp_path / "provider-grants.json"
        f.write_text("{oops")
        st = g.load_grant_config({g.ENV_PATH: str(f)})
        assert st.error and st.grants == ()

    def test_required_providers(self) -> None:
        assert g.required_providers({g.ENV_REQUIRED_FOR: " Anthropic, openai ,"}) == {
            "anthropic",
            "openai",
        }
        assert g.required_providers({}) == frozenset()


# ── Guard semantics ──────────────────────────────────────────────────────


class TestGuard:
    async def test_inert_when_nothing_configured(self, redis: Any) -> None:
        guard = _guard(redis, required=(), state=g.GrantConfigState())
        assert guard.enabled is False

    async def test_unguarded_provider_always_allowed(self, redis: Any) -> None:
        d = await _guard(redis, _grant_dict()).reserve("deepinfra", "madfam", None, _req())
        assert d.allowed and d.reservation is None

    async def test_no_grant_means_unavailable(self, redis: Any) -> None:
        guard = _guard(redis, state=g.GrantConfigState())
        d = await guard.reserve("anthropic", "madfam", "claude-opus-5-5", _req())
        assert not d.allowed and d.reason == "no_grant"

    async def test_wrong_org_unavailable(self, redis: Any) -> None:
        d = await _guard(redis, _grant_dict()).reserve("anthropic", "other-org", None, _req())
        assert not d.allowed and d.reason == "org_not_allowed"

    async def test_missing_org_unavailable(self, redis: Any) -> None:
        d = await _guard(redis, _grant_dict()).reserve("anthropic", None, None, _req(org=None))
        assert not d.allowed and d.reason == "org_missing"

    async def test_platform_org_alias(self, redis: Any) -> None:
        guard = g.GrantGuard(
            config_loader=lambda: _state(_grant_dict(allowed_orgs=["madfam"])),
            required=("anthropic",),
            meter=g.GrantMeter(redis),
            platform_orgs={"platform-uuid"},
            now_fn=_Clock(),
        )
        d = await guard.reserve("anthropic", "platform-uuid", "claude-opus-5-5", _req())
        assert d.allowed
        # An alias listed directly in allowed_orgs works without env.
        guard2 = _guard(redis, _grant_dict(allowed_orgs=["madfam", "janua-uuid"]))
        assert (await guard2.reserve("anthropic", "janua-uuid", None, _req())).allowed

    async def test_expired_unavailable(self, redis: Any) -> None:
        clock = _Clock(NOW + timedelta(days=2))
        d = await _guard(redis, _grant_dict(), clock=clock).reserve(
            "anthropic", "madfam", None, _req()
        )
        assert not d.allowed and d.reason == "expired"

    async def test_not_started_unavailable(self, redis: Any) -> None:
        clock = _Clock(NOW - timedelta(days=1))
        d = await _guard(redis, _grant_dict(), clock=clock).reserve(
            "anthropic", "madfam", None, _req()
        )
        assert not d.allowed and d.reason == "not_started"

    async def test_ceiling_unavailable(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict(amount_usd=1.0, safety_margin_usd=0.5))
        # 100k output tokens of an Opus-priced model is far above 0.50 USD.
        d = await guard.reserve("anthropic", "madfam", "claude-opus-4-7", _req(max_tokens=100_000))
        assert not d.allowed and d.reason == "ceiling_reached"

    async def test_invalid_config_unavailable(self, redis: Any) -> None:
        guard = _guard(redis, state=g.GrantConfigState(error="bad", source="test"))
        assert guard.enabled
        d = await guard.reserve("anthropic", "madfam", None, _req())
        assert not d.allowed and d.reason == "config_invalid"

    async def test_redis_down_unavailable(self) -> None:
        class _DeadScript:
            async def __call__(self, *a: Any, **k: Any) -> Any:
                raise ConnectionError("redis down")

        class _DeadRedis:
            def register_script(self, _lua: str) -> _DeadScript:
                return _DeadScript()

        guard = g.GrantGuard(
            config_loader=lambda: _state(_grant_dict()),
            required=("anthropic",),
            meter=g.GrantMeter(_DeadRedis()),
            platform_orgs={"madfam"},
            now_fn=_Clock(),
        )
        d = await guard.reserve("anthropic", "madfam", None, _req())
        assert not d.allowed and d.reason == "meter_unavailable"

    async def test_no_meter_unavailable(self) -> None:
        guard = g.GrantGuard(
            config_loader=lambda: _state(_grant_dict()),
            required=("anthropic",),
            meter_factory=lambda: None,
            platform_orgs={"madfam"},
            now_fn=_Clock(),
        )
        d = await guard.reserve("anthropic", "madfam", None, _req())
        assert not d.allowed and d.reason == "meter_unavailable"

    async def test_not_required_provider_passes_outside_grant(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict(), required=())
        d = await guard.reserve("anthropic", "other-org", None, _req())
        assert d.allowed and d.reservation is None and d.reason.startswith("unmetered")


# ── Pacer (Lua) ──────────────────────────────────────────────────────────


class TestPacer:
    async def test_concurrent_reservations_never_exceed_ceiling(self, redis: Any) -> None:
        grant = g.ProviderGrant.model_validate(
            _grant_dict(amount_usd=10.0, safety_margin_usd=0.0)
        )
        meter = g.GrantMeter(redis)
        results = await asyncio.gather(*(meter.try_reserve(grant, 1.0, NOW) for _ in range(50)))
        assert sum(1 for ok, _ in results if ok) == 10
        snap = await meter.snapshot(grant, NOW)
        assert snap.reserved_usd == pytest.approx(10.0)

    async def test_concurrent_guard_calls_respect_ceiling(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict(amount_usd=1.0, safety_margin_usd=0.0))
        req = _req(max_tokens=1000)
        worst = g.worst_case_cost_usd("anthropic", "claude-sonnet-4-6", req)
        assert worst is not None
        decisions = await asyncio.gather(
            *(guard.reserve("anthropic", "madfam", "claude-sonnet-4-6", req) for _ in range(150))
        )
        allowed = sum(1 for d in decisions if d.allowed)
        assert allowed == int(1.0 // worst)
        assert allowed * worst <= 1.0

    async def test_settle_and_release(self, redis: Any) -> None:
        grant = g.ProviderGrant.model_validate(_grant_dict())
        meter = g.GrantMeter(redis)
        ok, rid = await meter.try_reserve(grant, 2.0, NOW)
        assert ok and rid
        await meter.settle(grant, rid, 0.5, NOW)
        snap = await meter.snapshot(grant, NOW)
        assert snap.spent_usd == pytest.approx(0.5) and snap.reserved_usd == 0.0
        ok, rid2 = await meter.try_reserve(grant, 3.0, NOW)
        assert ok and rid2
        await meter.release(grant, rid2)
        snap = await meter.snapshot(grant, NOW)
        assert snap.spent_usd == pytest.approx(0.5) and snap.reserved_usd == 0.0

    async def test_reservations_expire_on_their_own(self, redis: Any) -> None:
        grant = g.ProviderGrant.model_validate(_grant_dict(amount_usd=10.0, safety_margin_usd=0))
        meter = g.GrantMeter(redis, reservation_ttl_seconds=30)
        assert (await meter.try_reserve(grant, 10.0, NOW))[0]
        assert not (await meter.try_reserve(grant, 1.0, NOW + timedelta(seconds=10)))[0]
        # The holder died: after the TTL the budget is free again.
        assert (await meter.try_reserve(grant, 10.0, NOW + timedelta(seconds=31)))[0]

    async def test_cold_start_seeds_from_ledger(self, redis: Any) -> None:
        grant = g.ProviderGrant.model_validate(_grant_dict(amount_usd=10.0, safety_margin_usd=0))

        async def seeder(_grant: g.ProviderGrant) -> float:
            return 9.5

        meter = g.GrantMeter(redis, seeder=seeder)
        assert not (await meter.try_reserve(grant, 1.0, NOW))[0]
        assert (await meter.snapshot(grant, NOW)).spent_usd == pytest.approx(9.5)

    async def test_seed_failure_seeds_zero_and_never_overwrites(self, redis: Any) -> None:
        grant = g.ProviderGrant.model_validate(_grant_dict())

        async def broken(_grant: g.ProviderGrant) -> float:
            raise OSError("ledger unreachable")

        meter = g.GrantMeter(redis, seeder=broken)
        ok, rid = await meter.try_reserve(grant, 1.0, NOW)
        assert ok and rid
        await meter.settle(grant, rid, 1.0, NOW)

        async def late(_grant: g.ProviderGrant) -> float:
            return 50.0

        meter.set_seeder(late)
        await meter.ensure_seeded(grant, NOW)
        assert (await meter.snapshot(grant, NOW)).spent_usd == pytest.approx(1.0)


# ── Status math (C2) ─────────────────────────────────────────────────────


class TestStatus:
    def _grant(self) -> g.ProviderGrant:
        return g.ProviderGrant.model_validate(_grant_dict())  # ceiling 95, 24 h window

    def test_pace_states(self) -> None:
        grant = self._grant()
        # 12 h left, 60 remaining → required 5 / h.
        assert g.pace_for(now=NOW, grant=grant, remaining_usd=60, burn_usd_per_hour=1)[0] == (
            "behind"
        )
        status, required = g.pace_for(
            now=NOW, grant=grant, remaining_usd=60, burn_usd_per_hour=5
        )
        assert status == "on_pace" and required == pytest.approx(5.0)
        assert g.pace_for(now=NOW, grant=grant, remaining_usd=60, burn_usd_per_hour=9)[0] == (
            "ahead"
        )
        assert g.pace_for(now=NOW, grant=grant, remaining_usd=0, burn_usd_per_hour=9)[0] == (
            "exhausted"
        )
        later = NOW + timedelta(days=1)
        assert g.pace_for(now=later, grant=grant, remaining_usd=60, burn_usd_per_hour=0)[0] == (
            "expired"
        )
        assert g.pace_for(now=NOW, grant=grant, remaining_usd=None, burn_usd_per_hour=None)[
            0
        ] == "unknown"

    def test_build_status_fields(self) -> None:
        snap = g.MeterSnapshot(spent_usd=30.0, reserved_usd=5.0, burn_usd_60m=5.0)
        st = g.build_status(self._grant(), snap, NOW)
        assert st.remaining_usd == pytest.approx(60.0)
        assert st.seconds_to_expiry == 12 * 3600
        assert st.required_usd_per_hour == pytest.approx(5.0)
        assert st.pace_status == "on_pace" and st.active and st.meter_ok

    def test_meter_down_is_visible(self) -> None:
        st = g.build_status(self._grant(), None, NOW)
        assert st.meter_ok is False and st.remaining_usd is None and st.pace_status == "unknown"

    async def test_burn_counts_last_60_minutes_only(self, redis: Any) -> None:
        clock = _Clock(NOW - timedelta(minutes=90))
        guard = _guard(redis, _grant_dict(), clock=clock)
        grant = guard.grants()[0]
        meter = guard.meter()
        assert meter is not None
        ok, rid = await meter.try_reserve(grant, 1.0, clock.now)
        assert rid
        await meter.settle(grant, rid, 4.0, clock.now)  # 90 min ago: out of window
        ok, rid = await meter.try_reserve(grant, 1.0, NOW)
        assert rid
        await meter.settle(grant, rid, 2.0, NOW - timedelta(minutes=10))
        clock.now = NOW
        [status] = await guard.statuses()
        assert status.spent_usd == pytest.approx(6.0)
        assert status.burn_usd_per_hour_60m == pytest.approx(2.0)


# ── Router integration ───────────────────────────────────────────────────


class _Provider(InferenceProvider):
    def __init__(self, name: str, *, fail: Exception | None = None) -> None:
        self.name = name
        self.fail = fail
        self.calls: list[str | None] = []

    async def complete(self, request: InferenceRequest) -> InferenceResponse:
        self.calls.append(request.policy.model_override)
        if self.fail is not None:
            raise self.fail
        return InferenceResponse(
            content="ok",
            model=request.policy.model_override or f"{self.name}-default",
            provider=self.name,
            usage={"input_tokens": 1000, "output_tokens": 500},
        )

    async def stream(
        self, request: InferenceRequest, on_usage: UsageCallback | None = None
    ) -> AsyncIterator[str]:
        self.calls.append(request.policy.model_override)
        if self.fail is not None:
            raise self.fail
        yield "chunk"
        if on_usage is not None:
            on_usage(
                StreamUsage(
                    input_tokens=1000,
                    output_tokens=500,
                    model=request.policy.model_override,
                )
            )

    async def list_models(self) -> list[str]:
        return []


def _router(guard: g.GrantGuard, **providers: _Provider) -> ModelRouter:
    org = OrgConfig(
        cloud_priority=["anthropic", "deepinfra"],
        model_assignments={
            TaskType.PLANNING: ModelAssignment(provider="anthropic", model="claude-opus-5-5"),
        },
    )
    return ModelRouter(providers=dict(providers), org_config=org, grant_guard=guard)


@pytest.fixture(autouse=True)
def _no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant(_s: float) -> None:
        return None

    monkeypatch.setattr("madfam_inference.router.asyncio.sleep", _instant)


class TestRouterHook:
    async def test_allowed_call_settles_actual_usd(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict())
        anth, deep = _Provider("anthropic"), _Provider("deepinfra")
        resp = await _router(guard, anthropic=anth, deepinfra=deep).complete(
            _req(task_type="planning")
        )
        assert resp.provider == "anthropic"
        [status] = await guard.statuses()
        assert status.spent_usd == pytest.approx(
            estimate_cost("anthropic", "claude-opus-5-5", 1000, 500)
        )
        assert status.reserved_usd == 0.0

    async def test_denied_falls_back_without_leaking_model(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict(), clock=_Clock(NOW + timedelta(days=3)))  # expired
        anth, deep = _Provider("anthropic"), _Provider("deepinfra")
        resp = await _router(guard, anthropic=anth, deepinfra=deep).complete(
            _req(task_type="planning")
        )
        assert resp.provider == "deepinfra"
        assert anth.calls == []
        assert deep.calls == [None]  # the claude assignment never reaches DeepInfra

    async def test_wrong_org_falls_back(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict())
        anth, deep = _Provider("anthropic"), _Provider("deepinfra")
        resp = await _router(guard, anthropic=anth, deepinfra=deep).complete(
            _req(task_type="planning", org="someone-else")
        )
        assert resp.provider == "deepinfra" and anth.calls == []

    async def test_pinned_model_errors_clearly(self, redis: Any) -> None:
        guard = _guard(redis, state=g.GrantConfigState())  # no grant at all
        anth, deep = _Provider("anthropic"), _Provider("deepinfra")
        router = _router(guard, anthropic=anth, deepinfra=deep)
        with pytest.raises(g.ProviderGrantUnavailableError) as info:
            await router.complete(_req(model_override="claude-opus-5-5"))
        assert "anthropic" in str(info.value) and "no_grant" in str(info.value)
        assert anth.calls == [] and deep.calls == []

    async def test_provider_error_releases_and_falls_back(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict())
        anth = _Provider("anthropic", fail=RuntimeError("upstream 529 overloaded"))
        deep = _Provider("deepinfra")
        resp = await _router(guard, anthropic=anth, deepinfra=deep).complete(
            _req(task_type="planning")
        )
        assert resp.provider == "deepinfra"
        assert len(anth.calls) == 2  # retry still reserved and released
        [status] = await guard.statuses()
        assert status.spent_usd == 0.0 and status.reserved_usd == 0.0

    async def test_restricted_never_touched_by_guard(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict())
        ollama = _Provider("ollama")
        router = _router(guard, anthropic=_Provider("anthropic"), ollama=ollama)
        resp = await router.complete(_req(sensitivity=Sensitivity.RESTRICTED, task_type="planning"))
        assert resp.provider == "ollama"

    async def test_allowlist_only_guarded_errors_with_reason(self, redis: Any) -> None:
        guard = _guard(redis, state=g.GrantConfigState())
        router = _router(guard, anthropic=_Provider("anthropic"), deepinfra=_Provider("deepinfra"))
        with pytest.raises(RuntimeError) as info:
            await router.complete(
                _req(provider_allowlist=["anthropic"], provider_models={"anthropic": "x"})
            )
        assert "anthropic (no_grant)" in str(info.value)

    async def test_stream_settles_usage(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict())
        router = _router(guard, anthropic=_Provider("anthropic"), deepinfra=_Provider("deepinfra"))
        chunks = [c async for c in router.stream(_req(task_type="planning"))]
        assert chunks == ["chunk"]
        [status] = await guard.statuses()
        assert status.spent_usd == pytest.approx(
            estimate_cost("anthropic", "claude-opus-5-5", 1000, 500)
        )

    async def test_stream_denied_falls_back(self, redis: Any) -> None:
        guard = _guard(redis, state=g.GrantConfigState())
        deep = _Provider("deepinfra")
        router = _router(guard, anthropic=_Provider("anthropic"), deepinfra=deep)
        chunks = [c async for c in router.stream(_req(task_type="planning"))]
        assert chunks == ["chunk"] and deep.calls == [None]

    async def test_disabled_guard_changes_nothing(self) -> None:
        guard = g.GrantGuard(
            config_loader=lambda: g.GrantConfigState(), required=(), meter_factory=lambda: None
        )
        anth = _Provider("anthropic")
        resp = await _router(guard, anthropic=anth, deepinfra=_Provider("deepinfra")).complete(
            _req(task_type="planning")
        )
        assert resp.provider == "anthropic" and anth.calls == ["claude-opus-5-5"]


class TestOrgOverrideInteraction:
    """LP's per-org overrides (#326) + the grant guard."""

    def _router(self, guard: g.GrantGuard, **providers: _Provider) -> ModelRouter:
        from madfam_inference.org_config import OrgOverride

        org = OrgConfig(
            cloud_priority=["deepinfra"],
            model_assignments={
                TaskType.PLANNING: ModelAssignment(provider="deepinfra", model="global-llama"),
            },
            org_overrides={
                "madfam": OrgOverride(
                    cloud_priority=["anthropic", "deepinfra"],
                    model_assignments={
                        TaskType.PLANNING: ModelAssignment(
                            provider="anthropic", model="claude-opus-5-5"
                        ),
                    },
                )
            },
        )
        return ModelRouter(providers=dict(providers), org_config=org, grant_guard=guard)

    async def test_override_used_under_live_grant(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict())
        anth, deep = _Provider("anthropic"), _Provider("deepinfra")
        resp = await self._router(guard, anthropic=anth, deepinfra=deep).complete(
            _req(task_type="planning")
        )
        assert resp.provider == "anthropic" and anth.calls == ["claude-opus-5-5"]

    async def test_dead_grant_falls_back_to_global_assignment_model(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict(), clock=_Clock(NOW + timedelta(days=3)))
        anth, deep = _Provider("anthropic"), _Provider("deepinfra")
        resp = await self._router(guard, anthropic=anth, deepinfra=deep).complete(
            _req(task_type="planning")
        )
        assert resp.provider == "deepinfra"
        assert anth.calls == [] and deep.calls == ["global-llama"]

    async def test_other_tenant_untouched(self, redis: Any) -> None:
        guard = _guard(redis, _grant_dict())
        anth, deep = _Provider("anthropic"), _Provider("deepinfra")
        resp = await self._router(guard, anthropic=anth, deepinfra=deep).complete(
            _req(task_type="planning", org="tenant-x")
        )
        assert resp.provider == "deepinfra" and deep.calls == ["global-llama"]
        [status] = await guard.statuses()
        assert status.spent_usd == 0.0


def test_guard_builds_one_meter_per_event_loop() -> None:
    """An asyncio Redis client is loop-bound; each running loop gets its own meter."""
    import asyncio

    from madfam_inference.grants import GrantGuard

    built: list[object] = []

    class _Meter:
        def __init__(self) -> None:
            self.seeder = None

        def set_seeder(self, seeder: object) -> None:
            self.seeder = seeder

    def factory() -> object:
        m = _Meter()
        built.append(m)
        return m

    guard = GrantGuard(required=["anthropic"], meter_factory=factory, platform_orgs=["madfam"])

    async def same_loop_twice() -> tuple[object, object]:
        return guard.meter(), guard.meter()

    a, b = asyncio.run(same_loop_twice())
    assert a is b
    (c, _) = asyncio.run(same_loop_twice())
    assert c is not a
    assert len(built) == 2
    # Outside any loop the guard keeps a single fallback meter.
    assert guard.meter() is guard.meter()
    assert all(isinstance(m, _Meter) for m in guard.all_meters())
