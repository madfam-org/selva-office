"""End-to-end integration tests for the task execution pipeline.

These tests call ``process_task()`` directly with mocked LLM, git, and
approval dependencies to verify the full lifecycle:
  dispatch -> worker -> graph -> completion
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _task_data(
    graph_type: str = "coding",
    task_id: str = "e2e-test-1",
    **extra: object,
) -> dict:
    return {
        "task_id": task_id,
        "graph_type": graph_type,
        "description": "E2E test task",
        "assigned_agent_ids": ["agent-1"],
        "payload": extra.get("payload", {}),
        "request_id": "req-e2e",
    }


def _perm_allow():
    from autoswarm_permissions.types import PermissionLevel

    perm_result = MagicMock()
    perm_result.level = PermissionLevel.ALLOW
    return perm_result


def _build_test_graph():
    """Build a coding graph without push_gate (avoids interrupt)."""
    from langgraph.graph import END, StateGraph

    from autoswarm_workers.graphs.coding import (
        CodingState,
        _route_after_implement,
        _route_after_test,
        implement,
        plan,
        review,
    )
    from autoswarm_workers.graphs.coding import (
        test as test_node,
    )

    graph = StateGraph(CodingState)
    graph.add_node("plan", plan)
    graph.add_node("implement", implement)
    graph.add_node("test", test_node)
    graph.add_node("review", review)
    graph.set_entry_point("plan")
    graph.add_edge("plan", "implement")
    graph.add_conditional_edges(
        "implement",
        _route_after_implement,
        {"test": "test", END: END},
    )
    graph.add_conditional_edges(
        "test",
        _route_after_test,
        {"review": "review", "implement": "implement"},
    )
    graph.add_edge("review", END)
    return graph


@pytest.mark.asyncio
async def test_coding_pipeline_mock_llm_succeeds(tmp_path):
    """Full coding lifecycle with mocked LLM returning valid JSON."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    valid_plan = json.dumps({
        "description": "test",
        "steps": ["Write main.py"],
    })
    valid_code = json.dumps({
        "files": [{"path": "main.py", "content": "print('hello')"}],
    })
    valid_review = json.dumps({
        "changes_reviewed": 1,
        "issues_found": 0,
        "recommendation": "approve",
    })

    call_idx = {"n": 0}

    async def mock_llm(router, messages, system_prompt, task_type):
        call_idx["n"] += 1
        if task_type == "planning":
            return valid_plan
        if task_type == "coding":
            return valid_code
        return valid_review

    git_instance = MagicMock()
    git_instance.create_worktree = AsyncMock(return_value=str(wt))
    git_instance.cleanup_worktree = AsyncMock()

    with (
        patch("autoswarm_workers.__main__._update_task_status", new_callable=AsyncMock),
        patch("autoswarm_workers.__main__._publish_agent_status", new_callable=AsyncMock),
        patch("autoswarm_workers.__main__._emit_event", new_callable=AsyncMock),
        patch(
            "autoswarm_workers.__main__._fetch_agent_skills",
            new_callable=AsyncMock,
            return_value=[],
        ),
        patch("autoswarm_workers.__main__.get_redis_pool", return_value=MagicMock()),
        patch("autoswarm_observability.bind_task_context"),
        patch("autoswarm_observability.clear_context"),
        patch("autoswarm_workers.inference.get_model_router", return_value=MagicMock()),
        patch("autoswarm_workers.inference.call_llm", side_effect=mock_llm),
        patch("autoswarm_workers.tools.git_tool.GitTool", return_value=git_instance),
        patch("autoswarm_workers.graphs.coding.check_permission", return_value=_perm_allow()),
        patch("autoswarm_workers.__main__.GRAPH_BUILDERS", {"coding": _build_test_graph}),
    ):
        from autoswarm_workers.__main__ import process_task

        data = _task_data(payload={"repo_path": str(repo)})
        await process_task(data)

    assert call_idx["n"] >= 2


@pytest.mark.asyncio
async def test_coding_pipeline_timeout(tmp_path):
    """Task exceeding timeout -> status 'failed'."""
    import autoswarm_workers.__main__ as worker_mod

    repo = tmp_path / "repo"
    repo.mkdir()

    update_status = AsyncMock()

    async def slow_graph(*args, **kwargs):
        await asyncio.sleep(10)
        return {"status": "completed"}

    with (
        patch.object(worker_mod, "_update_task_status", update_status),
        patch.object(worker_mod, "_publish_agent_status", new_callable=AsyncMock),
        patch.object(worker_mod, "_emit_event", new_callable=AsyncMock),
        patch.object(
            worker_mod, "_fetch_agent_skills",
            new_callable=AsyncMock, return_value=[],
        ),
        patch.object(worker_mod, "get_redis_pool", return_value=MagicMock()),
        patch("autoswarm_observability.bind_task_context"),
        patch("autoswarm_observability.clear_context"),
        patch.object(
            worker_mod, "run_graph_with_interrupts", side_effect=slow_graph,
        ),
        patch.object(worker_mod, "get_task_timeout", return_value=0.1),
    ):
        data = _task_data(graph_type="research")
        await worker_mod.process_task(data)

    update_status.assert_awaited()
    calls = update_status.call_args_list
    final_call = calls[-1]
    assert final_call.args[2] == "failed"
