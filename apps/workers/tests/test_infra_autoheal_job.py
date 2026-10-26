"""Worker job for the infra self-healing agent (RFC 0047).

Funded-credential selection, the router-backed model client, and one
incident end to end with test doubles (no network, no DB, no chat).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import fakeredis.aioredis
import pytest
import pytest_asyncio
from selva_autoheal.agent import DiagnosisAgent, LLMReply, LLMUnavailable
from selva_autoheal.alerts import AlertmanagerWebhook, normalise
from selva_autoheal.config import AutohealConfig
from selva_autoheal.store import QUEUE_KEY, IncidentStore
from selva_autoheal.tools import Toolbox

from madfam_inference.types import InferenceResponse
from selva_workers.jobs import infra_autoheal as job

FIXTURES = Path(__file__).resolve().parents[3] / "packages/autoheal/tests/fixtures"


def _cfg(**overrides: Any) -> AutohealConfig:
    base: dict[str, Any] = {
        "enabled": True,
        "incident_cap_usd": 1.0,  # placeholders
        "daily_cap_usd": 5.0,
        "alertnames": ("CNPGInstanceStatusUnreachable",),
        "courier_url": "https://courier.invalid",
        "courier_tenant": "tenant-placeholder",
        "courier_recipient": "chat-placeholder",
    }
    base.update(overrides)
    return AutohealConfig(**base)


def _status(provider: str, **overrides: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "provider": provider,
        "active": True,
        "meter_ok": True,
        "remaining_usd": 10.0,
        "pace_status": "behind",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


@pytest_asyncio.fixture
async def redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


class TestFundedProviders:
    PREFS = ("anthropic-ops", "anthropic")

    def test_only_live_funded_grants_in_preference_order(self) -> None:
        statuses = [
            _status("anthropic", active=False, pace_status="expired"),
            _status("anthropic-ops"),
        ]
        assert job.funded_from_statuses(self.PREFS, statuses) == ("anthropic-ops",)

    def test_both_funded_keeps_the_order(self) -> None:
        statuses = [_status("anthropic"), _status("anthropic-ops")]
        assert job.funded_from_statuses(self.PREFS, statuses) == self.PREFS

    @pytest.mark.parametrize(
        "overrides",
        [
            {"remaining_usd": 0.0},
            {"remaining_usd": None, "meter_ok": False},
            {"pace_status": "exhausted"},
            {"pace_status": "unknown"},
            {"active": False},
        ],
    )
    def test_unfunded_or_unreadable_is_left_out(self, overrides: dict[str, Any]) -> None:
        statuses = [_status("anthropic-ops", **overrides)]
        assert job.funded_from_statuses(self.PREFS, statuses) == ()

    def test_provider_without_a_grant_is_left_out(self) -> None:
        assert job.funded_from_statuses(self.PREFS, [_status("deepinfra")]) == ()


class _FakeRouter:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.requests: list[Any] = []

    async def complete(self, request: Any) -> Any:
        self.requests.append(request)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class TestRouterLLM:
    async def _call(
        self, monkeypatch: pytest.MonkeyPatch, result: Any
    ) -> tuple[Any, list[Any], list[dict[str, Any]]]:
        router = _FakeRouter(result)
        metered: list[dict[str, Any]] = []

        async def meter(**kwargs: Any) -> None:
            metered.append(kwargs)

        monkeypatch.setattr("selva_workers.inference.get_model_router", lambda: router)
        monkeypatch.setattr("selva_workers.metering.meter_inference_call", meter)
        reply = await job.RouterLLM(_cfg(), "task-1").complete(
            system="s",
            messages=[{"role": "user", "content": "x"}],
            providers=("anthropic-ops", "anthropic"),
            model="claude-sonnet-5-5",
            max_tokens=512,
            incident_key="inc-1",
        )
        return reply, router.requests, metered

    async def test_policy_is_server_set_and_spend_is_metered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        response = InferenceResponse(
            content="{}", model="claude-sonnet-5-5", provider="anthropic-ops",
            usage={"input_tokens": 100, "output_tokens": 20},
        )
        reply, requests, metered = await self._call(monkeypatch, response)
        assert isinstance(reply, LLMReply) and reply.provider == "anthropic-ops"
        policy = requests[0].policy
        assert policy.org_id == "madfam"
        assert policy.provider_allowlist == ["anthropic-ops", "anthropic"]
        assert policy.provider_models == {
            "anthropic-ops": "claude-sonnet-5-5", "anthropic": "claude-sonnet-5-5"
        }
        assert metered[0]["provider"] == "anthropic-ops" and metered[0]["task_id"] == "task-1"

    @pytest.mark.parametrize(
        ("error", "no_budget"),
        [
            (RuntimeError("No available provider for sensitivity=internal. Grant-guarded and "
                          "unavailable: anthropic-ops (ceiling_reached)."), True),
            (RuntimeError("upstream exploded"), False),
            (TimeoutError(), False),
        ],
    )
    async def test_errors_map_to_llm_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception, no_budget: bool
    ) -> None:
        with pytest.raises(LLMUnavailable) as info:
            await self._call(monkeypatch, error)
        assert info.value.no_budget is no_budget

    async def test_grant_unavailable_error_is_no_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from madfam_inference.grants import ProviderGrantUnavailableError

        with pytest.raises(LLMUnavailable) as info:
            await self._call(monkeypatch, ProviderGrantUnavailableError("expired"))
        assert info.value.no_budget is True


class _Enclii:
    def __init__(self) -> None:
        self.responses = json.loads(
            (FIXTURES / "cnpg_operator_ingress_2026-10-24.enclii.json").read_text()
        )

    async def __call__(self, method: str, path: str, body: Any) -> tuple[int, Any]:
        assert method == "GET" or body["dry_run"] is True
        ns = ((body or {}).get("scope") or {}).get("namespace")
        for key in (f"{method} {path}#{ns}", f"{method} {path}"):
            if key in self.responses:
                return 200, self.responses[key]
        return 404, {}


class _LLM:
    async def complete(self, **kwargs: Any) -> LLMReply:
        final = {"action": "final", "summary": "s", "root_cause": "r", "confidence": "high",
                 "evidence": ["E2"], "remedy": None}
        return LLMReply(json.dumps(final), kwargs["providers"][0], kwargs["model"],
                        {"input_tokens": 3000, "output_tokens": 300})


async def test_run_incident_end_to_end(redis: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg()
    store = IncidentStore(redis, cfg)
    payload = json.loads(
        (FIXTURES / "cnpg_operator_ingress_2026-10-24.alertmanager.json").read_text()
    )
    signal = normalise(AlertmanagerWebhook.model_validate(payload))

    async def funded(p: tuple[str, ...]) -> tuple[str, ...]:
        return p[:1]

    sent: list[dict[str, Any]] = []

    async def post(url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
        sent.append(body)
        return 201, {"delivery": {"id": "dlv-1"}}

    agent = DiagnosisAgent(cfg, Toolbox(_Enclii()), _LLM(), job._price, funded, store.killed)
    monkeypatch.setenv("COURIER_API_KEY", "producer-key-placeholder")
    record = await job.run_incident(cfg, store, signal, agent=agent, post=post, record_db=False)

    assert record["state"] == "reported"
    assert record["report"]["status"] == "diagnosed"
    assert record["delivery"]["sent"] is True and record["delivery"]["delivery_id"] == "dlv-1"
    assert sent[0]["recipient"]["ref"] == "chat-placeholder"
    assert signal.key in sent[0]["body"]["text"]
    stored = await store.record(signal.key)
    assert stored is not None and stored["state"] == "reported"
    spent = await store.spend_today(datetime.now(tz=UTC))
    assert spent == pytest.approx(record["report"]["spent_usd"]) and spent > 0


async def test_rediagnosis_threads_under_the_first_report(
    redis: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _cfg(courier_threading=True)
    store = IncidentStore(redis, cfg)
    payload = json.loads(
        (FIXTURES / "cnpg_operator_ingress_2026-10-24.alertmanager.json").read_text()
    )
    signal = normalise(AlertmanagerWebhook.model_validate(payload))

    async def funded(p: tuple[str, ...]) -> tuple[str, ...]:
        return ()

    sent: list[dict[str, Any]] = []

    async def post(url: str, headers: dict[str, str], body: dict[str, Any]) -> tuple[int, Any]:
        sent.append(body)
        return 201, {"delivery": {"id": f"0000000{len(sent)}-0000-4000-8000-000000000000"}}

    monkeypatch.setenv("COURIER_API_KEY", "producer-key-placeholder")
    for _ in range(2):
        agent = DiagnosisAgent(cfg, Toolbox(_Enclii()), _LLM(), job._price, funded, store.killed)
        await job.run_incident(cfg, store, signal, agent=agent, post=post, record_db=False)
    assert "reply_to" not in sent[0]
    assert sent[1]["reply_to"] == {"delivery_id": "00000001-0000-4000-8000-000000000000"}


async def test_run_incident_without_courier_is_recorded_not_dropped(redis: Any) -> None:
    cfg = _cfg(courier_url="")
    store = IncidentStore(redis, cfg)
    payload = json.loads(
        (FIXTURES / "cnpg_operator_ingress_2026-10-24.alertmanager.json").read_text()
    )
    signal = normalise(AlertmanagerWebhook.model_validate(payload))

    async def unfunded(p: tuple[str, ...]) -> tuple[str, ...]:
        return ()

    agent = DiagnosisAgent(cfg, Toolbox(_Enclii()), _LLM(), job._price, unfunded, store.killed)
    record = await job.run_incident(cfg, store, signal, agent=agent, record_db=False)
    assert record["report"]["status"] == "sin_presupuesto"
    assert record["delivery"]["status"] == "not_configured"


async def test_tick_with_empty_queue_releases_the_lock(redis: Any) -> None:
    assert await job.tick(_cfg(), redis) is None
    assert not await redis.exists(job.LOCK_KEY)
    assert await redis.llen(QUEUE_KEY) == 0


async def test_disabled_loop_returns_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    monkeypatch.delenv("INFRA_AUTOHEAL_ENABLED", raising=False)
    await asyncio.wait_for(job.periodic_loop(asyncio.Event()), timeout=1)


async def test_enabled_without_caps_stays_idle(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import asyncio

    monkeypatch.setenv("INFRA_AUTOHEAL_ENABLED", "true")
    await asyncio.wait_for(job.periodic_loop(asyncio.Event()), timeout=1)
    assert "NOT running" in caplog.text
