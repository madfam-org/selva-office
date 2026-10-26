"""The toolbox refuses every write, every secret and everything unlisted.

A refusal never reaches the network and is audited.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from selva_autoheal.testing import NOW, RecordedEnclii, ScriptedLLM, make_cfg, price
from selva_autoheal.agent import DiagnosisAgent
from selva_autoheal.alerts import AlertmanagerWebhook, normalise
from selva_autoheal.tools import (
    READ_OPS,
    REMEDY_DRY_RUN_OPS,
    Toolbox,
    redact,
)


@pytest.mark.parametrize(
    ("tool", "args"),
    [
        ("kubectl", {"cmd": "delete pod x"}),
        ("enclii_apply", {"domain": "pods", "action": "restart"}),
        ("enclii_ops_read", {"domain": "pods", "action": "restart", "target": "x"}),
        ("enclii_ops_read", {"domain": "secrets", "action": "external"}),
        ("enclii_ops_read", {"domain": "secrets", "action": "vault"}),
        ("enclii_ops_read", {"domain": "apps", "action": "sync", "namespace": "n"}),
        ("enclii_ops_read", {"domain": "apps", "action": "status", "dry_run": False}),
        ("enclii_ops_read", {"domain": "apps", "action": "status", "expected_plan": "h"}),
        ("enclii_ops_read", {"domain": "apps", "action": "status", "reason": "apply now"}),
        ("enclii_remedy_dry_run", {"domain": "pods", "action": "restart", "target": "x",
                                   "dry_run": False}),
        ("enclii_remedy_dry_run", {"domain": "pods", "action": "restart", "target": "x",
                                   "expected_plan": "sha256:x"}),
        ("enclii_remedy_dry_run", {"domain": "storage", "action": "pvc-apply", "target": "x"}),
        ("enclii_remedy_dry_run", {"domain": "pods", "action": "restart"}),  # no target
        ("enclii_get", {"path": "/v1/services/00000000-0000-0000-0000-000000000000/env-vars"}),
        ("enclii_get", {"path": "/v1/projects/demo/secrets"}),
        ("enclii_get", {"path": "/v1/projects/demo/../admin/drift"}),
        ("enclii_get", {"path": "/v1/projects/demo/addons?include=credentials"}),
        ("enclii_get", {"path": "/v1/admin/topology"}),
        ("enclii_get", {"path": "/v1/projects/demo", "method": "DELETE"}),
    ],
)
async def test_refused_before_the_network(tool: str, args: dict[str, Any]) -> None:
    enclii = RecordedEnclii({})
    box = Toolbox(enclii)
    outcome = await box.call(tool, args)
    assert outcome.refused and not outcome.ok and outcome.text.startswith("REFUSED")
    assert enclii.requests == []
    assert box.audit[-1]["refused"] is True


async def test_every_allowlisted_read_is_sent_as_dry_run() -> None:
    enclii = RecordedEnclii({})
    box = Toolbox(enclii)
    for domain, action in sorted(READ_OPS):
        await box.call("enclii_ops_read", {"domain": domain, "action": action, "namespace": "n"})
    for domain, action in sorted(REMEDY_DRY_RUN_OPS):
        await box.call("enclii_remedy_dry_run",
                       {"domain": domain, "action": action, "namespace": "n", "target": "t"})
    assert len(enclii.requests) == len(READ_OPS) + len(REMEDY_DRY_RUN_OPS)
    for method, path, body in enclii.requests:
        assert method == "POST" and body is not None
        assert body["dry_run"] is True
        assert set(body) == {"operation", "dry_run", "scope", "args"}
        assert body["operation"] == "ops." + path.removeprefix("/v1/ops/").replace("/", ".")


def test_no_secret_domain_or_apply_op_is_allowlisted() -> None:
    for domain, action in READ_OPS | REMEDY_DRY_RUN_OPS:
        assert domain != "secrets"
        assert not action.endswith("-apply") and action not in ("retire", "rollback")


async def test_allowlisted_get_paths_are_sent() -> None:
    enclii = RecordedEnclii({})
    box = Toolbox(enclii)
    for path in (
        "/v1/projects/demo/addons",
        "/v1/addons/00000000-0000-0000-0000-000000000000/events",
        "/v1/services/00000000-0000-0000-0000-000000000000/health/detailed",
        "/v1/observability/alerts",
    ):
        outcome = await box.call("enclii_get", {"path": path})
        assert not outcome.refused
    assert [m for m, _, _ in enclii.requests] == ["GET"] * 4


async def test_tail_lines_are_capped_and_stringified() -> None:
    enclii = RecordedEnclii({})
    await Toolbox(enclii).call(
        "enclii_ops_read",
        {"domain": "pods", "action": "logs", "namespace": "n", "target": "p", "tail_lines": 99999},
    )
    assert enclii.requests[0][2]["args"] == {"target": "p", "tailLines": "300"}


async def test_inventory_is_narrowed_to_the_namespace(enclii: RecordedEnclii) -> None:
    outcome = await Toolbox(enclii).call(
        "enclii_ops_read",
        {"domain": "inventory", "action": "network-policies", "namespace": "project-example01"},
    )
    groups = outcome.data["data"]["groups"]
    assert [g["namespace"] for g in groups] == ["project-example01"]
    assert "other-namespace" not in outcome.text


def test_redaction() -> None:
    text = redact('{"api_key": "sk-live-abc", "password":"hunter2", "blob": "' + "A" * 60 + '"}')
    assert "sk-live-abc" not in text and "hunter2" not in text and "A" * 60 not in text


async def test_unconfigured_enclii_is_an_outcome_not_a_crash() -> None:
    outcome = await Toolbox(None).call(
        "enclii_ops_read", {"domain": "apps", "action": "status", "namespace": "n"}
    )
    assert not outcome.ok and "not configured" in outcome.text


async def test_model_asking_for_a_write_is_refused_and_the_run_continues(
    alert_payload: dict[str, Any], enclii: RecordedEnclii
) -> None:
    """The planted log line asks for a restart with dry_run false: refused."""

    async def funded(p: tuple[str, ...]) -> tuple[str, ...]:
        return p

    async def alive() -> bool:
        return False

    attack = json.dumps(
        {"action": "call_tool", "tool": "enclii_remedy_dry_run",
         "args": {"domain": "pods", "action": "restart", "target": "app-db-1",
                  "dry_run": False}}
    )
    final = json.dumps({"action": "final", "summary": "s", "root_cause": "r",
                        "confidence": "medium", "evidence": ["E2"], "remedy": None})
    llm = ScriptedLLM([attack, final])
    agent = DiagnosisAgent(make_cfg(), Toolbox(enclii), llm, price, funded, alive,
                           now=lambda: NOW)
    signal = normalise(AlertmanagerWebhook.model_validate(alert_payload))
    report = await agent.run(signal, 0.0)
    assert report.status == "diagnosed"
    refused = [a for a in report.audit["tools"] if a["refused"]]
    assert len(refused) == 1 and refused[0]["tool"] == "enclii_remedy_dry_run"
    assert all(p != "/v1/ops/pods/restart" for _, p, _ in enclii.requests)
    # The refusal is fed back to the model as data.
    assert "REFUSED" in llm.calls[1]["messages"][-1]["content"]
