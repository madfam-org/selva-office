"""Budget caps, stop conditions, flap protection, kill switch, config gates."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest

from selva_autoheal.testing import NOW, RecordedEnclii, ScriptedLLM, make_cfg, price
from selva_autoheal import intake
from selva_autoheal.agent import DiagnosisAgent, LLMUnavailable
from selva_autoheal.alerts import AlertmanagerWebhook, normalise
from selva_autoheal.budget import BudgetExceeded, IncidentBudget
from selva_autoheal.config import AutohealConfig, ConfigError
from selva_autoheal.store import KILL_KEY, IncidentStore
from selva_autoheal.tools import Toolbox

TOOL_CALL = json.dumps(
    {"action": "call_tool", "tool": "enclii_ops_read",
     "args": {"domain": "apps", "action": "status", "namespace": "project-example01"}}
)


async def _funded(providers: tuple[str, ...]) -> tuple[str, ...]:
    return providers


async def _alive() -> bool:
    return False


def _signal(alert_payload: dict[str, Any]) -> Any:
    return normalise(AlertmanagerWebhook.model_validate(alert_payload))


def _agent(enclii: RecordedEnclii, llm: ScriptedLLM, **cfg: Any) -> DiagnosisAgent:
    return DiagnosisAgent(make_cfg(**cfg), Toolbox(enclii), llm, price, _funded, _alive,
                          now=lambda: NOW)


# ── Budget ───────────────────────────────────────────────────────────────


class TestBudget:
    def test_admits_worst_case_under_both_caps(self) -> None:
        b = IncidentBudget(cap_usd=1.0, daily_cap_usd=5.0, spent_today_usd=0.0, price=price)
        worst = b.admit("anthropic-ops", "claude-sonnet-5-5", 30_000, 2048)
        assert worst == pytest.approx(price("anthropic-ops", "claude-sonnet-5-5", 10_001, 2048))

    def test_incident_cap(self) -> None:
        b = IncidentBudget(cap_usd=0.01, daily_cap_usd=5.0, spent_today_usd=0.0, price=price)
        with pytest.raises(BudgetExceeded) as info:
            b.admit("anthropic-ops", "claude-opus-5-5", 300_000, 8192)
        assert info.value.reason == "incident_cap"

    def test_daily_cap_counts_spend_already_made_today(self) -> None:
        b = IncidentBudget(cap_usd=1.0, daily_cap_usd=1.0, spent_today_usd=0.99, price=price)
        with pytest.raises(BudgetExceeded) as info:
            b.admit("anthropic-ops", "claude-sonnet-5-5", 30_000, 2048)
        assert info.value.reason == "daily_cap"

    async def test_agent_stops_at_the_incident_cap_before_calling(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        llm = ScriptedLLM([TOOL_CALL] * 10)
        report = await _agent(enclii, llm, incident_cap_usd=0.05, daily_cap_usd=5.0).run(
            _signal(alert_payload), 0.0
        )
        assert report.status == "stopped" and report.stop_reason == "incident_cap"
        assert report.spent_usd <= 0.05
        assert len(llm.calls) == report.llm_calls < 10

    async def test_agent_respects_the_daily_cap(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        llm = ScriptedLLM([TOOL_CALL])
        report = await _agent(enclii, llm, daily_cap_usd=1.0).run(_signal(alert_payload), 0.999)
        assert report.stop_reason == "daily_cap" and llm.calls == []


# ── Stop conditions ──────────────────────────────────────────────────────


class TestStops:
    async def test_step_limit(self, alert_payload: dict[str, Any], enclii: RecordedEnclii) -> None:
        llm = ScriptedLLM([TOOL_CALL] * 5, usage={"input_tokens": 10, "output_tokens": 10})
        report = await _agent(enclii, llm, max_steps=3).run(_signal(alert_payload), 0.0)
        assert report.stop_reason == "step_limit" and len(llm.calls) == 3

    async def test_time_limit(self, alert_payload: dict[str, Any], enclii: RecordedEnclii) -> None:
        clock = iter([0.0, 1000.0, 2000.0, 3000.0])
        agent = _agent(enclii, ScriptedLLM([TOOL_CALL] * 3), max_seconds=60)
        agent.monotonic = lambda: next(clock)
        report = await agent.run(_signal(alert_payload), 0.0)
        assert report.stop_reason == "time_limit" and report.llm_calls == 0

    async def test_kill_switch_before_any_read(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        async def killed() -> bool:
            return True

        agent = _agent(enclii, ScriptedLLM([TOOL_CALL]))
        agent.killed = killed
        report = await agent.run(_signal(alert_payload), 0.0)
        assert report.stop_reason == "kill_switch" and enclii.requests == []

    async def test_kill_switch_mid_run(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        flips = iter([False, False, True])

        async def killed() -> bool:
            return next(flips, True)

        llm = ScriptedLLM([TOOL_CALL] * 5, usage={"input_tokens": 10, "output_tokens": 10})
        agent = _agent(enclii, llm)
        agent.killed = killed
        report = await agent.run(_signal(alert_payload), 0.0)
        assert report.stop_reason == "kill_switch" and len(llm.calls) == 1

    async def test_unparseable_replies_stop(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        llm = ScriptedLLM(["not json"] * 5, usage={"input_tokens": 10, "output_tokens": 10})
        report = await _agent(enclii, llm).run(_signal(alert_payload), 0.0)
        assert report.stop_reason == "unparseable_replies" and len(llm.calls) == 3

    async def test_grant_refusal_mid_run_is_sin_presupuesto(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        llm = ScriptedLLM(
            [LLMUnavailable("provider_grant_unavailable: ceiling_reached", no_budget=True)]
        )
        report = await _agent(enclii, llm).run(_signal(alert_payload), 0.0)
        assert report.status == "sin_presupuesto" and report.spent_usd == 0.0
        assert report.signatures == ["cnpg-operator-ingress-blocked"]

    async def test_provider_error_is_not_mislabelled_as_budget(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        llm = ScriptedLLM([LLMUnavailable("HTTP 529 overloaded")])
        report = await _agent(enclii, llm).run(_signal(alert_payload), 0.0)
        assert report.status == "stopped" and report.stop_reason == "llm_unavailable"


# ── Intake: dedup, cooldown, flap protection, daily limit, kill switch ───


class TestIntake:
    async def test_repeat_notification_is_a_duplicate(
        self, alert_payload: dict[str, Any], redis: Any
    ) -> None:
        cfg = make_cfg()
        store = IncidentStore(redis, cfg)
        first = await intake.handle(alert_payload, store, cfg, NOW)
        again = await intake.handle(alert_payload, store, cfg, NOW + timedelta(minutes=5))
        assert (first.decision, again.decision) == ("queued", "duplicate")
        assert first.incident_key == again.incident_key
        assert await store.pop() is not None and await store.pop() is None

    async def test_flapping_key_stops_being_diagnosed(
        self, alert_payload: dict[str, Any], redis: Any
    ) -> None:
        cfg = make_cfg(cooldown_seconds=1, max_runs_per_key_per_day=2)
        store = IncidentStore(redis, cfg)
        decisions = []
        for _ in range(3):
            await redis.delete(f"selva:autoheal:cooldown:{_signal(alert_payload).key}")
            decisions.append((await intake.handle(alert_payload, store, cfg, NOW)).decision)
        assert decisions == ["queued", "queued", "flapping"]

    async def test_daily_incident_limit(self, alert_payload: dict[str, Any], redis: Any) -> None:
        cfg = make_cfg(max_incidents_per_day=1)
        store = IncidentStore(redis, cfg)
        other = {**alert_payload, "groupKey": alert_payload["groupKey"] + "-other"}
        assert (await intake.handle(alert_payload, store, cfg, NOW)).decision == "queued"
        assert (await intake.handle(other, store, cfg, NOW)).decision == "daily_limit"

    async def test_kill_switch_records_but_queues_nothing(
        self, alert_payload: dict[str, Any], redis: Any
    ) -> None:
        cfg = make_cfg()
        store = IncidentStore(redis, cfg)
        await redis.set(KILL_KEY, "1")
        result = await intake.handle(alert_payload, store, cfg, NOW)
        assert result.decision == "killed" and await store.pop() is None
        record = await store.record(result.incident_key)
        assert record is not None and record["state"] == "killed"

    async def test_unlisted_alert_is_ignored(
        self, alert_payload: dict[str, Any], redis: Any
    ) -> None:
        cfg = make_cfg(alertnames=("SomethingElse",))
        result = await intake.handle(alert_payload, IncidentStore(redis, cfg), cfg, NOW)
        assert (result.decision, result.reason) == ("ignored", "alertname_not_allowlisted")

    async def test_resolved_notification_closes_the_record(
        self, alert_payload: dict[str, Any], redis: Any
    ) -> None:
        cfg = make_cfg()
        store = IncidentStore(redis, cfg)
        opened = await intake.handle(alert_payload, store, cfg, NOW)
        resolved = await intake.handle({**alert_payload, "status": "resolved"}, store, cfg, NOW)
        assert resolved.decision == "resolved"
        record = await store.record(opened.incident_key)
        assert record is not None and record["state"] == "resolved"

    async def test_invalid_payload_names_fields_not_values(self, redis: Any) -> None:
        cfg = make_cfg()
        with pytest.raises(intake.InvalidPayload) as info:
            await intake.handle({"status": "firing"}, IncidentStore(redis, cfg), cfg, NOW)
        assert "groupKey" in str(info.value)


# ── Config gates ─────────────────────────────────────────────────────────


class TestConfig:
    def test_off_by_default(self) -> None:
        cfg = AutohealConfig.from_env({})
        assert cfg.enabled is False
        with pytest.raises(ConfigError):
            cfg.validate_for_run()

    def test_enabled_without_caps_refuses_to_run(self) -> None:
        cfg = AutohealConfig.from_env(
            {"INFRA_AUTOHEAL_ENABLED": "true",
             "INFRA_AUTOHEAL_ALERTNAMES": "CNPGInstanceStatusUnreachable"}
        )
        with pytest.raises(ConfigError) as info:
            cfg.validate_for_run()
        assert "INCIDENT_CAP_USD" in str(info.value) and "DAILY_CAP_USD" in str(info.value)

    def test_enabled_without_alertnames_refuses_to_run(self) -> None:
        cfg = make_cfg(alertnames=())
        with pytest.raises(ConfigError):
            cfg.validate_for_run()

    def test_incident_cap_above_daily_cap_is_refused(self) -> None:
        with pytest.raises(ConfigError):
            make_cfg(incident_cap_usd=10.0, daily_cap_usd=1.0).validate_for_run()

    def test_from_env_reads_preference_order(self) -> None:
        cfg = AutohealConfig.from_env({"INFRA_AUTOHEAL_PROVIDERS": "anthropic-ops, anthropic"})
        assert cfg.providers == ("anthropic-ops", "anthropic")
        assert cfg.no_budget == "stop"

    async def test_disabled_agent_does_no_work(
        self, alert_payload: dict[str, Any], enclii: RecordedEnclii
    ) -> None:
        agent = _agent(enclii, ScriptedLLM([TOOL_CALL]), enabled=False)
        with pytest.raises(ConfigError):
            await agent.run(_signal(alert_payload), 0.0)
        assert enclii.requests == []
