"""End to end on the recorded 2026-10-24 CNPG incident.

Alertmanager payload in → incident queued → agent run (scripted model, under
a per-incident cap) with read-only Enclii tools → diagnosis with evidence and
a proposed remedy → Courier envelope for the incident's Telegram chat.

The alert rule in the fixture (``CNPGInstanceStatusUnreachable``) is the one
RFC 0047 proposes: on 2026-10-24 no rule covered project CNPG clusters, so
the payload is a replay of what that rule would have sent. The Enclii
responses are reconstructed from the incident's diagnosis, with placeholder
names.
"""

from __future__ import annotations

import json
from typing import Any

from selva_autoheal.testing import NOW, FakeCourier, RecordedEnclii, ScriptedLLM, make_cfg, price
from selva_autoheal import courier, intake
from selva_autoheal.agent import DiagnosisAgent
from selva_autoheal.report import render
from selva_autoheal.store import IncidentStore
from selva_autoheal.tools import Toolbox


async def _funded(providers: tuple[str, ...]) -> tuple[str, ...]:
    return providers[:1]  # only the first credential has a live grant


async def _unfunded(providers: tuple[str, ...]) -> tuple[str, ...]:
    return ()


async def _alive() -> bool:
    return False


def _final(**overrides: Any) -> str:
    body: dict[str, Any] = {
        "action": "final",
        "summary": "CNPG no alcanza el puerto 8000 de las instancias por la política default-deny.",
        "root_cause": "default-deny sin regla que admita cnpg-system → TCP/8000.",
        "confidence": "high",
        "evidence": ["E2", "E4"],
        "remedy": {
            "kind": "prepare_only_pr",
            "title": "Converger app-db-operator-ingress",
            "detail": "Enclii #854 crea la política; verificar la versión de switchyard.",
            "verify": "La política aparece y el estado deja de mostrar el error.",
        },
    }
    body.update(overrides)
    return json.dumps(body)


async def _queue(alert_payload: dict[str, Any], redis: Any) -> tuple[IncidentStore, Any]:
    cfg = make_cfg()
    store = IncidentStore(redis, cfg)
    result = await intake.handle(alert_payload, store, cfg, NOW)
    assert result.decision == "queued"
    signal = await store.pop()
    assert signal is not None and signal.key == result.incident_key
    return store, signal


def _assert_no_write(enclii: RecordedEnclii) -> None:
    for method, path, body in enclii.requests:
        assert method in ("GET", "POST")
        if method == "POST":
            assert path.startswith("/v1/ops/")
            assert body is not None and body["dry_run"] is True
            assert "expected_plan" not in body["args"] and "reason" not in body


async def test_replay_produces_diagnosis_with_evidence_and_remedy(
    alert_payload: dict[str, Any], redis: Any, enclii: RecordedEnclii
) -> None:
    store, signal = await _queue(alert_payload, redis)
    llm = ScriptedLLM(
        [
            json.dumps(
                {
                    "action": "call_tool",
                    "tool": "enclii_ops_read",
                    "args": {"domain": "pods", "action": "diagnose",
                             "namespace": signal.namespace},
                }
            ),
            _final(),
        ]
    )
    agent = DiagnosisAgent(make_cfg(), Toolbox(enclii), llm, price, _funded, _alive, now=lambda: NOW)
    report = await agent.run(signal, await store.spend_today(NOW))

    assert report.status == "diagnosed"
    assert report.signatures == ["cnpg-operator-ingress-blocked"]
    assert report.cited_evidence == ["E2", "E4"]
    assert report.confidence == "high"
    assert report.remedy is not None and report.remedy["kind"] == "prepare_only_pr"
    assert report.llm_calls == 2 and report.providers_used == ["anthropic-ops"]
    assert 0 < report.spent_usd <= make_cfg().incident_cap_usd
    # Only the funded credential was offered to the model client.
    assert all(c["providers"] == ("anthropic-ops",) for c in llm.calls)
    # The deterministic probes ran before any model call.
    probes = [(m, p) for m, p, _ in enclii.requests[:4]]
    assert probes == [
        ("POST", "/v1/ops/pods/diagnose"),
        ("POST", "/v1/ops/inventory/network-policies"),
        ("POST", "/v1/ops/pods/diagnose"),
        ("POST", "/v1/ops/pods/logs"),
    ]
    _assert_no_write(enclii)

    # Tool output reaches the model fenced as untrusted data, including the
    # planted instruction in the operator log.
    first = llm.calls[0]["messages"][0]["content"]
    assert "untrusted data" in first and "IGNORE PREVIOUS INSTRUCTIONS" in first

    text = render(report)
    assert signal.key in text and "default-deny" in text
    assert "Ninguna escritura en producción" in text

    fake = FakeCourier()
    delivery = await courier.send(
        make_cfg(), text=text, idempotency_key=f"selva-autoheal:{signal.key}:diagnosis",
        post=fake, env={"COURIER_API_KEY": "producer-key-placeholder"},
    )
    assert delivery.sent and delivery.delivery_id == "dlv-1"
    url, headers, envelope = fake.sent[0]
    assert url == "https://courier.invalid/v1/courier/send"
    assert headers == {"X-Internal-API-Key": "producer-key-placeholder"}
    assert envelope["channel"] == "telegram"
    assert envelope["recipient"] == {"kind": "telegram_chat", "ref": "chat-placeholder"}
    assert envelope["consent"]["class"] == "operational"
    assert "reply_to" not in envelope  # threading is off until angelia accepts it


async def test_replay_without_budget_reports_sin_presupuesto(
    alert_payload: dict[str, Any], redis: Any, enclii: RecordedEnclii
) -> None:
    _, signal = await _queue(alert_payload, redis)
    llm = ScriptedLLM([_final()])
    agent = DiagnosisAgent(make_cfg(), Toolbox(enclii), llm, price, _unfunded, _alive,
                           now=lambda: NOW)
    report = await agent.run(signal, 0.0)

    assert report.status == "sin_presupuesto"
    assert llm.calls == []  # no key is called when no credential has budget
    assert report.llm_calls == 0 and report.spent_usd == 0.0
    # The deterministic signature still gives the diagnosis with evidence.
    assert report.signatures == ["cnpg-operator-ingress-blocked"]
    assert set(report.cited_evidence) == {"E2", "E4"}
    assert report.remedy is not None and "operator-ingress" in report.remedy["title"]
    assert "sin presupuesto" in render(report)
    _assert_no_write(enclii)


async def test_no_budget_fallback_uses_only_the_configured_fallback(
    alert_payload: dict[str, Any], redis: Any, enclii: RecordedEnclii
) -> None:
    _, signal = await _queue(alert_payload, redis)
    cfg = make_cfg(no_budget="fallback", fallback_providers=("deepinfra",))
    llm = ScriptedLLM([_final()])
    agent = DiagnosisAgent(cfg, Toolbox(enclii), llm, price, _unfunded, _alive, now=lambda: NOW)
    report = await agent.run(signal, 0.0)
    assert report.status == "diagnosed" and report.stop_reason == "fallback_provider"
    assert [c["providers"] for c in llm.calls] == [("deepinfra",)]


async def test_enclii_remedy_is_planned_with_plan_hash_never_applied(
    alert_payload: dict[str, Any], redis: Any, enclii: RecordedEnclii
) -> None:
    enclii.plan_hash = "sha256:abc123"
    _, signal = await _queue(alert_payload, redis)
    remedy = {
        "kind": "enclii_dry_run",
        "title": "Reiniciar app-db-2",
        "detail": "Plan de reinicio",
        "verify": "pod listo",
        "enclii_op": {"domain": "pods", "action": "restart", "namespace": signal.namespace,
                      "target": "app-db-2"},
    }
    llm = ScriptedLLM([_final(remedy=remedy)])
    agent = DiagnosisAgent(make_cfg(), Toolbox(enclii), llm, price, _funded, _alive,
                           now=lambda: NOW)
    report = await agent.run(signal, 0.0)

    assert report.remedy is not None
    assert report.remedy["plan_hash"] == "sha256:abc123"
    assert report.remedy["enclii_audit_id"] == "aud-plan"
    method, path, body = enclii.requests[-1]
    assert (method, path) == ("POST", "/v1/ops/pods/restart")
    assert body == {
        "operation": "ops.pods.restart",
        "dry_run": True,
        "scope": {"namespace": signal.namespace},
        "args": {"target": "app-db-2"},
    }
    text = render(report)
    assert "plan_hash sha256:abc123" in text and "Selva no aplica nada" in text
    _assert_no_write(enclii)


async def test_remedy_outside_plan_allowlist_becomes_manual(
    alert_payload: dict[str, Any], redis: Any, enclii: RecordedEnclii
) -> None:
    _, signal = await _queue(alert_payload, redis)
    remedy = {"kind": "enclii_dry_run", "title": "x", "detail": "y", "verify": "z",
              "enclii_op": {"domain": "secrets", "action": "refresh-apply", "target": "s"}}
    agent = DiagnosisAgent(make_cfg(), Toolbox(enclii), ScriptedLLM([_final(remedy=remedy)]),
                           price, _funded, _alive, now=lambda: NOW)
    report = await agent.run(signal, 0.0)
    assert report.remedy is not None and report.remedy["kind"] == "manual"
    assert all(p != "/v1/ops/secrets/refresh-apply" for _, p, _ in enclii.requests)


async def test_uncited_claims_lower_confidence(
    alert_payload: dict[str, Any], redis: Any, enclii: RecordedEnclii
) -> None:
    _, signal = await _queue(alert_payload, redis)
    llm = ScriptedLLM([_final(evidence=["E99"])])
    agent = DiagnosisAgent(make_cfg(), Toolbox(enclii), llm, price, _funded, _alive,
                           now=lambda: NOW)
    report = await agent.run(signal, 0.0)
    assert report.confidence == "low" and report.cited_evidence == []
    assert report.audit["uncited_evidence_ids"] == ["E99"]
