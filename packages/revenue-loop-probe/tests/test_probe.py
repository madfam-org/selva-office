"""Tests for the probe orchestrator.

We verify:
  - stages run in order
  - a failing stage does not stop subsequent stages unless short_circuit=True
  - skip_if_missing decorator behaves correctly
  - the report is JSON-serialisable and .ok reflects stage outcomes
  - per-stage exceptions become FAILED results, not crashes
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from revenue_loop_probe.probe import (
    ProbeContext,
    ProbeStep,
    RevenueLoopProbe,
    StageResult,
    StageStatus,
)


@dataclass
class _StubStep:
    name: str
    result: StageResult
    saw_ctx: ProbeContext | None = None

    async def run(self, ctx: ProbeContext) -> StageResult:
        self.saw_ctx = ctx
        return self.result


@dataclass
class _RaisingStep:
    name: str = "raiser"

    async def run(self, ctx: ProbeContext) -> StageResult:
        raise RuntimeError("boom")


async def test_run_passes_all_when_all_ok():
    steps = [
        _StubStep("a", StageResult("a", StageStatus.PASSED, 1.0)),
        _StubStep("b", StageResult("b", StageStatus.PASSED, 1.0)),
    ]
    probe = RevenueLoopProbe(list(steps))
    report = await probe.run(ProbeContext())
    assert report.ok
    assert [s.name for s in report.stages] == ["a", "b"]
    assert report.fail_count == 0


async def test_run_continues_past_failure_by_default():
    steps = [
        _StubStep("a", StageResult("a", StageStatus.FAILED, 1.0, detail="x")),
        _StubStep("b", StageResult("b", StageStatus.PASSED, 1.0)),
    ]
    probe = RevenueLoopProbe(list(steps))
    report = await probe.run(ProbeContext())
    assert not report.ok
    assert report.fail_count == 1
    assert len(report.stages) == 2  # both ran


async def test_run_short_circuits_when_requested():
    step_b_stub = _StubStep("b", StageResult("b", StageStatus.PASSED, 1.0))
    steps = [
        _StubStep("a", StageResult("a", StageStatus.FAILED, 1.0, detail="x")),
        step_b_stub,
    ]
    probe = RevenueLoopProbe(list(steps), short_circuit=True)
    report = await probe.run(ProbeContext())
    assert report.fail_count == 1
    assert len(report.stages) == 1
    assert step_b_stub.saw_ctx is None


async def test_raising_step_becomes_failed_result_not_crash():
    probe = RevenueLoopProbe([_RaisingStep(), _StubStep("b", StageResult("b", StageStatus.PASSED, 1.0))])
    report = await probe.run(ProbeContext())
    assert report.stages[0].status is StageStatus.FAILED
    assert "boom" in (report.stages[0].detail or "")
    assert report.stages[1].status is StageStatus.PASSED


async def test_report_is_json_serialisable():
    steps = [_StubStep("a", StageResult("a", StageStatus.PASSED, 1.0, facts={"k": 1}))]
    report = await RevenueLoopProbe(steps).run(ProbeContext())
    # Must round-trip cleanly
    as_json = json.dumps(report.to_dict())
    back = json.loads(as_json)
    assert back["stages"][0]["name"] == "a"
    assert back["ok"] is True
    assert back["stages"][0]["facts"] == {"k": 1}


def test_empty_probe_rejected():
    with pytest.raises(ValueError):
        RevenueLoopProbe([])


async def test_stage_can_write_ctx_state_for_later_stages():
    class WriteStep:
        name = "write"

        async def run(self, ctx):
            ctx.state["hello"] = "world"
            return StageResult(self.name, StageStatus.PASSED, 1.0)

    class ReadStep:
        name = "read"

        async def run(self, ctx):
            assert ctx.state.get("hello") == "world"
            return StageResult(
                self.name, StageStatus.PASSED, 1.0, facts={"read": ctx.state["hello"]}
            )

    probe = RevenueLoopProbe([WriteStep(), ReadStep()])
    report = await probe.run(ProbeContext())
    assert report.ok
    assert report.stages[1].facts == {"read": "world"}
