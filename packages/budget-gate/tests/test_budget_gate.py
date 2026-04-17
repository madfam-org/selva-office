from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from madfam_budget_gate.gate import (
    BudgetDenied,
    BudgetExceededError,
    _challenge_string,
    new_tracker,
    require_approval,
)


def test_challenge_string_depends_on_estimate(cheap_estimate):
    challenge_a = _challenge_string(cheap_estimate, "exp1")
    challenge_b = _challenge_string(cheap_estimate, "exp2")
    assert challenge_a != challenge_b, "challenge must differ per experiment"


def test_challenge_changes_if_cost_changes(tiny_pricing):
    from madfam_budget_gate.cost_model import RunShape, estimate

    base = estimate(
        RunShape("tiny-model", 1, 1, 1, 1000, 100), tiny_pricing
    )
    bigger = estimate(
        RunShape("tiny-model", 1, 1, 1, 10_000, 100), tiny_pricing
    )
    assert _challenge_string(base, "x") != _challenge_string(bigger, "x")


def test_approval_happy_path_writes_audit_record(gate_cfg, cheap_estimate):
    challenge = _challenge_string(cheap_estimate, gate_cfg.experiment_id)
    out = io.StringIO()
    inp = io.StringIO(challenge + "\n")
    record = require_approval(
        cheap_estimate, gate_cfg, input_stream=inp, output_stream=out
    )
    assert record.experiment_id == "test-exp"
    assert abs(record.approved_cap_usd - cheap_estimate.total_usd) < 1e-9
    # Audit file exists and is valid JSON
    files = list(gate_cfg.approvals_dir.glob("*.json"))
    assert len(files) == 1
    data = json.loads(files[0].read_text())
    assert data["challenge"] == challenge
    # Summary is printed
    assert "META-HARNESS BUDGET GATE" in out.getvalue()
    assert challenge in out.getvalue()


def test_approval_refuses_wrong_input(gate_cfg, cheap_estimate):
    inp = io.StringIO("yes please\n")
    with pytest.raises(BudgetDenied, match="did not match"):
        require_approval(cheap_estimate, gate_cfg, input_stream=inp, output_stream=io.StringIO())
    # No audit file
    assert list(gate_cfg.approvals_dir.glob("*.json")) == []


def test_approval_refuses_empty_input(gate_cfg, cheap_estimate):
    inp = io.StringIO("\n")
    with pytest.raises(BudgetDenied):
        require_approval(cheap_estimate, gate_cfg, input_stream=inp, output_stream=io.StringIO())


def test_approval_refuses_when_over_hard_cap(gate_cfg, over_cap_estimate):
    # Whatever challenge the user types, the cap check fires first.
    challenge = _challenge_string(over_cap_estimate, gate_cfg.experiment_id)
    inp = io.StringIO(challenge + "\n")
    with pytest.raises(BudgetDenied, match="exceeds hard cap"):
        require_approval(
            over_cap_estimate, gate_cfg, input_stream=inp, output_stream=io.StringIO()
        )


def test_env_config_requires_owner(monkeypatch, tmp_path: Path):
    from madfam_budget_gate.gate import GateConfig

    monkeypatch.setenv("MADFAM_BUDGET_HARD_CAP_USD", "10")
    monkeypatch.setenv("MADFAM_EXPERIMENT_ID", "x")
    monkeypatch.setenv("MADFAM_EXPERIMENT_OWNER", "")
    monkeypatch.setenv("MADFAM_APPROVALS_DIR", str(tmp_path / "a"))
    monkeypatch.setenv("MADFAM_LOGS_DIR", str(tmp_path / "l"))
    with pytest.raises(BudgetDenied, match="OWNER"):
        GateConfig.from_env()


def test_env_config_requires_hard_cap(monkeypatch, tmp_path: Path):
    from madfam_budget_gate.gate import GateConfig

    monkeypatch.delenv("MADFAM_BUDGET_HARD_CAP_USD", raising=False)
    monkeypatch.setenv("MADFAM_EXPERIMENT_ID", "x")
    monkeypatch.setenv("MADFAM_EXPERIMENT_OWNER", "y")
    with pytest.raises(BudgetDenied, match="HARD_CAP"):
        GateConfig.from_env()


def test_env_config_rejects_wild_grace_factor(monkeypatch, tmp_path: Path):
    from madfam_budget_gate.gate import GateConfig

    monkeypatch.setenv("MADFAM_BUDGET_HARD_CAP_USD", "5")
    monkeypatch.setenv("MADFAM_BUDGET_GRACE_FACTOR", "5.0")
    monkeypatch.setenv("MADFAM_EXPERIMENT_ID", "x")
    monkeypatch.setenv("MADFAM_EXPERIMENT_OWNER", "y")
    with pytest.raises(BudgetDenied, match="GRACE_FACTOR"):
        GateConfig.from_env()


def test_spend_tracker_accumulates_and_logs(gate_cfg, cheap_estimate):
    challenge = _challenge_string(cheap_estimate, gate_cfg.experiment_id)
    record = require_approval(
        cheap_estimate,
        gate_cfg,
        input_stream=io.StringIO(challenge + "\n"),
        output_stream=io.StringIO(),
    )
    tracker = new_tracker(record, gate_cfg)
    tracker.record_usage(model="x", input_tokens=1000, output_tokens=100, usd=0.001, tag="t1")
    tracker.record_usage(model="x", input_tokens=2000, output_tokens=200, usd=0.002, tag="t2")
    snap = tracker.snapshot()
    assert snap["total_input_tokens"] == 3000
    assert snap["total_output_tokens"] == 300
    assert abs(snap["total_usd"] - 0.003) < 1e-9
    assert snap["killed"] is False
    # Log file is JSONL
    lines = tracker.log_path.read_text().strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        json.loads(line)


def test_spend_tracker_trips_kill_when_over_cap(gate_cfg, cheap_estimate):
    challenge = _challenge_string(cheap_estimate, gate_cfg.experiment_id)
    record = require_approval(
        cheap_estimate,
        gate_cfg,
        input_stream=io.StringIO(challenge + "\n"),
        output_stream=io.StringIO(),
    )
    tracker = new_tracker(record, gate_cfg)
    # Approved cost is cheap ($0.014 from conftest); kill at 1.10x.
    # First call well under cap — should be fine.
    tracker.record_usage(model="x", input_tokens=1, output_tokens=1, usd=0.001, tag="t1")
    # Force a record that pushes us over 1.10x approved.
    with pytest.raises(BudgetExceededError):
        tracker.record_usage(model="x", input_tokens=1, output_tokens=1, usd=999.0, tag="boom")
    # Next call must also fail — tracker is sticky.
    with pytest.raises(BudgetExceededError):
        tracker.record_usage(model="x", input_tokens=1, output_tokens=1, usd=0.001, tag="late")
    assert tracker.snapshot()["killed"] is True
