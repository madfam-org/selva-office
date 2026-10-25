"""Impeccable on UI/UX tasks: skill loading, detector gate, findings loop."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.graph import END

from selva_workers import ui_audit

_FINDING = {
    "rule": "overused-font",
    "name": "Overused font",
    "severity": "warning",
    "category": "slop",
    "file": "web/globals.css",
    "line": 3,
    "snippet": "font-family: 'Inter",
    "advisory": False,
}
_ADVISORY = {**_FINDING, "rule": "em-dash-overuse", "advisory": True, "severity": "advisory"}


def _report(findings: list[dict[str, Any]]) -> dict[str, Any]:
    primary = [f for f in findings if not f["advisory"]]
    return {
        "status": "findings" if primary else "clean",
        "findings": findings,
        "primary_count": len(primary),
        "advisory_count": len(findings) - len(primary),
        "files_scanned": ["web/globals.css"],
        "engine_version": "0.1.16",
        "npm_version": "4.7.0",
        "telemetry": "off",
    }


def _ui_state(**extra: Any) -> dict[str, Any]:
    return {
        "messages": [],
        "task_id": "t-ui",
        "worktree_path": "/tmp/wt",
        "iteration": 1,
        "agent_skill_ids": ["coding"],
        "agent_system_prompt": "## Skill: coding\n\ncoding rules",
        "code_changes": [{"iteration": 1, "files_modified": ["web/globals.css", "api.py"]}],
        "audience": "tenant",
        **extra,
    }


# -- task fields + skill loading ---------------------------------------------------------


def test_ui_task_fields_loads_command_reference() -> None:
    fields = ui_audit.ui_task_fields("coding", {"impeccable_command": "polish"}, "Refactor")
    assert fields["ui_ux_task"] is True
    assert fields["impeccable_command"] == "polish"
    assert fields["impeccable_reference"].startswith("## Skill reference: impeccable `polish`")


def test_ui_task_fields_for_non_ui_task() -> None:
    fields = ui_audit.ui_task_fields("coding", {}, "Tune the Redis pool backoff")
    assert fields == {"ui_ux_task": False, "impeccable_command": "", "impeccable_reference": ""}


def test_ui_task_fields_rejects_unknown_command() -> None:
    with pytest.raises(ValueError):
        ui_audit.ui_task_fields("coding", {"impeccable_command": "sparkle"}, "")


# -- ui_audit node ------------------------------------------------------------------------


def test_non_ui_task_without_ui_files_is_untouched() -> None:
    state = _ui_state(code_changes=[{"files_modified": ["api.py"]}])
    with patch.object(ui_audit, "_detect") as detect:
        assert ui_audit.run_ui_audit(state) is state
    detect.assert_not_called()


def test_changed_ui_files_make_the_task_ui_and_load_the_skill() -> None:
    with patch.object(ui_audit, "_detect", return_value=_report([_FINDING])) as detect:
        out = ui_audit.run_ui_audit(_ui_state())
    detect.assert_called_once_with("/tmp/wt", ["web/globals.css"])
    assert out["ui_ux_task"] is True
    assert out["agent_skill_ids"] == ["coding", "impeccable"]
    assert "## Skill: impeccable" in out["agent_system_prompt"]
    assert out["agent_system_prompt"].startswith("## Skill: coding")
    assert out["ui_audit"]["status"] == "findings"
    assert out["ui_audit"]["rounds"] == 1
    msg = out["messages"][-1]
    assert "1 primary" in msg.content
    assert msg.additional_kwargs["action_category"] == "file_read"


def test_detector_crash_is_reported_not_clean() -> None:
    with patch.object(ui_audit, "_detect", side_effect=RuntimeError("boom")):
        out = ui_audit.run_ui_audit(_ui_state(ui_ux_task=True))
    assert out["ui_audit"]["status"] == "error"
    assert "deterministic scan unavailable" in out["messages"][-1].content


def test_ui_task_without_worktree_is_unavailable() -> None:
    with patch.object(ui_audit, "_detect") as detect:
        out = ui_audit.run_ui_audit(_ui_state(ui_ux_task=True, worktree_path=None))
    detect.assert_not_called()
    assert out["ui_audit"]["status"] == "unavailable"


# -- findings loop -------------------------------------------------------------------------


def test_findings_route_back_to_implement_once() -> None:
    first = {"ui_audit": {**_report([_FINDING]), "rounds": 1}, "iteration": 1}
    second = {"ui_audit": {**_report([_FINDING]), "rounds": 2}, "iteration": 2}
    clean = {"ui_audit": {**_report([_ADVISORY]), "rounds": 1}, "iteration": 1}
    capped = {"ui_audit": {**_report([_FINDING]), "rounds": 1}, "iteration": 3}
    assert ui_audit.route_after_ui_audit(first) == "implement"
    assert ui_audit.route_after_ui_audit(second) == "review"
    assert ui_audit.route_after_ui_audit(clean) == "review"
    assert ui_audit.route_after_ui_audit(capped) == "review"


def test_findings_are_fed_into_the_implement_prompt() -> None:
    state = _ui_state(
        ui_audit={**_report([_FINDING, _ADVISORY]), "rounds": 1},
        impeccable_reference="## Skill reference: impeccable `polish`",
    )
    ctx = ui_audit.skill_context(state, "implement")
    assert "## Skill: coding" in ctx
    assert "impeccable `polish`" in ctx
    assert "Impeccable detector findings to fix" in ctx
    assert "`overused-font` at web/globals.css:3" in ctx
    assert "em-dash-overuse" not in ctx  # advisories never drive a fix round
    assert "findings to fix" not in ui_audit.skill_context(state, "plan")


def test_review_asks_for_justifications() -> None:
    state = _ui_state(ui_audit={**_report([_FINDING]), "rounds": 2})
    ctx = ui_audit.skill_context(state, "review")
    assert "Impeccable UI/UX gate" in ctx
    assert "ui_findings_justification" in ctx


# -- review finalization + enforcement --------------------------------------------------------


def test_warn_mode_reports_unjustified_findings_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ui_audit.ENFORCEMENT_ENV, raising=False)
    state = _ui_state(ui_audit={**_report([_FINDING]), "rounds": 2})
    updates = ui_audit.finalize_after_review(state, {"recommendation": "approve"})
    assert "status" not in updates
    assert updates["ui_audit"]["unjustified_count"] == 1
    assert updates["ui_audit"]["remaining"][0]["rule"] == "overused-font"


def test_justified_findings_pass_block_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ui_audit.ENFORCEMENT_ENV, "block")
    state = _ui_state(ui_audit={**_report([_FINDING]), "rounds": 2})
    review = {
        "ui_findings_justification": [
            {
                "rule": "overused-font",
                "file": "web/globals.css",
                "line": 3,
                "justification": "Brand typeface mandated by DESIGN.md",
            }
        ]
    }
    updates = ui_audit.finalize_after_review(state, review)
    assert "status" not in updates
    assert updates["ui_audit"]["unjustified_count"] == 0
    assert updates["ui_audit"]["justifications"][0]["justification"].startswith("Brand")


def test_block_mode_blocks_unjustified_or_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ui_audit.ENFORCEMENT_ENV, "block")
    blocked = ui_audit.finalize_after_review(
        _ui_state(ui_audit={**_report([_FINDING]), "rounds": 2}), {}
    )
    assert blocked["status"] == "blocked"
    assert "1 unjustified" in blocked["result"]["error"]
    unavailable = ui_audit.finalize_after_review(
        _ui_state(ui_audit={"status": "unavailable", "error": "no binary", "rounds": 1}), {}
    )
    assert unavailable["status"] == "blocked"
    assert "no binary" in unavailable["result"]["error"]


def test_non_ui_review_is_unchanged() -> None:
    assert ui_audit.finalize_after_review({"messages": []}, {}) == {}
    assert ui_audit.review_section({}) == ""
    assert ui_audit.approval_summary({}) is None


# -- graph wiring -----------------------------------------------------------------------------


def test_coding_graph_routes_through_ui_audit() -> None:
    from selva_workers.graphs import coding

    graph = coding.build_coding_graph()
    assert {"ui_audit", "review", "push_gate"} <= set(graph.nodes)
    assert coding._route_after_test({"test_results": {"passed": True}}) == "ui_audit"
    assert coding._route_after_test({"test_results": {"passed": False}, "iteration": 3}) == (
        "ui_audit"
    )
    assert coding._route_after_review({"status": "blocked"}) == END
    assert coding._route_after_review({"status": "reviewed"}) == "push_gate"


def test_push_gate_shows_the_ui_gate_to_the_approver() -> None:
    from selva_workers.graphs import coding

    state = _ui_state(ui_audit={**_report([_FINDING]), "rounds": 2, "unjustified_count": 1})
    with patch.object(coding, "interrupt", return_value={"approved": False}) as gate:
        coding.push_gate.__wrapped__(state)  # type: ignore[attr-defined]
    context = gate.call_args.args[0]
    assert context["ui_audit"]["status"] == "findings"
    assert context["ui_audit"]["remaining"][0]["rule"] == "overused-font"


# -- end to end through process_task ------------------------------------------------------------


def _graph_without_push_gate():
    from langgraph.graph import StateGraph

    from selva_workers.graphs import coding

    graph = StateGraph(coding.CodingState)
    for name in ("plan", "implement", "test", "ui_audit", "review"):
        graph.add_node(name, getattr(coding, name))
    graph.set_entry_point("plan")
    graph.add_edge("plan", "implement")
    graph.add_conditional_edges(
        "implement", coding._route_after_implement, {"test": "test", END: END}
    )
    graph.add_conditional_edges(
        "test", coding._route_after_test, {"ui_audit": "ui_audit", "implement": "implement"}
    )
    graph.add_conditional_edges(
        "ui_audit",
        coding._route_after_ui_audit,
        {"review": "review", "implement": "implement"},
    )
    graph.add_edge("review", END)
    return graph


async def test_ui_task_loads_impeccable_and_feeds_findings_back(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    prompts: dict[str, list[str]] = {"planning": [], "coding": [], "review": []}

    async def fake_llm(router, messages, system_prompt="", task_type="coding", **kwargs):
        prompts.setdefault(task_type, []).append(system_prompt)
        if task_type == "planning":
            return json.dumps({"description": "d", "steps": ["Restyle", "Fix findings"]})
        if task_type == "coding":
            return json.dumps(
                {"files": [{"path": "web/globals.css", "content": "body{font-family:x}"}]}
            )
        return json.dumps(
            {
                "changes_reviewed": 2,
                "issues_found": 0,
                "recommendation": "approve",
                "ui_findings_justification": [],
            }
        )

    reports = iter([_report([_FINDING]), _report([])])
    git_instance = MagicMock()
    git_instance.create_worktree = AsyncMock(return_value=str(wt))
    bash_ok = MagicMock(success=True, stdout="1 passed", stderr="", return_code=0)
    perm = MagicMock()
    from selva_permissions.types import PermissionLevel

    perm.level = PermissionLevel.ALLOW
    status_mock = AsyncMock()

    with (
        patch("selva_workers.__main__._update_task_status", status_mock),
        patch("selva_workers.__main__._publish_agent_status", new_callable=AsyncMock),
        patch("selva_workers.__main__._emit_event", new_callable=AsyncMock),
        patch(
            "selva_workers.__main__._fetch_agent_skills",
            new_callable=AsyncMock,
            return_value=["coding"],
        ),
        patch("selva_workers.__main__.get_redis_pool", return_value=MagicMock()),
        patch("selva_observability.bind_task_context"),
        patch("selva_observability.clear_context"),
        patch("selva_workers.inference.get_model_router", return_value=MagicMock()),
        patch("selva_workers.inference.call_llm", side_effect=fake_llm),
        patch("selva_workers.tools.git_tool.GitTool", return_value=git_instance),
        patch("selva_workers.graphs.coding.check_permission", return_value=perm),
        patch("selva_workers.graphs.coding._bash_tool.execute", AsyncMock(return_value=bash_ok)),
        patch.object(ui_audit, "_detect", side_effect=lambda wt_, files: next(reports)),
        patch("selva_workers.__main__.GRAPH_BUILDERS", {"coding": _graph_without_push_gate}),
    ):
        from selva_workers.__main__ import process_task

        await process_task(
            {
                "task_id": "e2e-ui",
                "graph_type": "coding",
                "description": "Polish the settings page",
                "assigned_agent_ids": ["agent-1"],
                "payload": {"repo_path": str(repo), "impeccable_command": "polish"},
                "request_id": "req-ui",
            }
        )

    # The impeccable skill + the polish reference were in the plan prompt.
    assert "## Skill: impeccable" in prompts["planning"][0]
    assert "impeccable `polish`" in prompts["planning"][0]
    # Detector findings reached the second implement iteration only.
    assert len(prompts["coding"]) == 2
    assert "findings to fix" not in prompts["coding"][0]
    assert "`overused-font` at web/globals.css:3" in prompts["coding"][1]
    # The review saw the (now clean) gate; the task result carries it.
    assert "Impeccable UI/UX gate" in prompts["review"][0]
    final_call = status_mock.await_args_list[-1]
    api_result = final_call.args[3]
    assert api_result["ui_audit"]["status"] == "clean"
    assert api_result["ui_audit"]["rounds"] == 2
    assert api_result["ui_audit"]["telemetry"] == "off"


async def test_unknown_command_fails_the_task_before_running() -> None:
    status_mock = AsyncMock()
    with (
        patch("selva_workers.__main__._update_task_status", status_mock),
        patch("selva_workers.__main__._publish_agent_status", new_callable=AsyncMock),
        patch("selva_workers.__main__._emit_event", new_callable=AsyncMock),
        patch("selva_workers.__main__._fetch_agent_skills", new_callable=AsyncMock) as fetch,
        patch("selva_observability.bind_task_context"),
    ):
        from selva_workers.__main__ import process_task

        await process_task(
            {
                "task_id": "bad-cmd",
                "graph_type": "coding",
                "description": "x",
                "assigned_agent_ids": ["agent-1"],
                "payload": {"impeccable_command": "sparkle"},
            }
        )
    fetch.assert_not_called()
    assert status_mock.await_args.args[2] == "failed"
    assert "unknown impeccable_command" in status_mock.await_args.args[3]["error"]
