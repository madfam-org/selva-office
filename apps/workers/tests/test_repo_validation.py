"""Tests for repo path validation before coding tasks."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_non_writable_repo_path_fails_task() -> None:
    """When the repo path is not writable, the task should be failed immediately."""
    from autoswarm_workers.__main__ import process_task

    task_data = {
        "task_id": "test-task-1",
        "graph_type": "coding",
        "description": "Fix a bug",
        "assigned_agent_ids": ["agent-1"],
        "payload": {"repo_path": "/nonexistent/readonly/path"},
    }

    with (
        patch("autoswarm_workers.__main__._update_task_status", new_callable=AsyncMock) as mock_status,
        patch("autoswarm_workers.__main__._publish_agent_status", new_callable=AsyncMock),
        patch("autoswarm_workers.__main__._emit_event", new_callable=AsyncMock),
        patch("autoswarm_workers.__main__._fetch_agent_skills", new_callable=AsyncMock, return_value=[]),
    ):
        await process_task(task_data)

    # The task should have been marked as failed.
    mock_status.assert_called()
    last_call = mock_status.call_args_list[-1]
    assert last_call[0][2] == "failed"  # status arg
    assert "not writable" in str(last_call[1].get("error_message", "") or last_call[0][3])


@pytest.mark.asyncio
async def test_missing_repo_path_created() -> None:
    """When repo path doesn't exist yet, it should be created."""
    from autoswarm_workers.__main__ import process_task

    with tempfile.TemporaryDirectory() as tmpdir:
        new_path = Path(tmpdir) / "new-repos"
        assert not new_path.exists()

        task_data = {
            "task_id": "test-task-2",
            "graph_type": "coding",
            "description": "Add feature",
            "assigned_agent_ids": ["agent-1"],
            "payload": {"repo_path": str(new_path)},
        }

        with (
            patch("autoswarm_workers.__main__._update_task_status", new_callable=AsyncMock),
            patch("autoswarm_workers.__main__._publish_agent_status", new_callable=AsyncMock),
            patch("autoswarm_workers.__main__._emit_event", new_callable=AsyncMock),
            patch("autoswarm_workers.__main__._fetch_agent_skills", new_callable=AsyncMock, return_value=[]),
            patch("autoswarm_workers.__main__.run_graph_with_interrupts", new_callable=AsyncMock, return_value={"status": "completed"}),
            patch("autoswarm_workers.__main__.InterruptHandler") as mock_handler_cls,
        ):
            mock_handler = AsyncMock()
            mock_handler_cls.return_value = mock_handler

            await process_task(task_data)

        # The directory should have been created.
        assert new_path.exists()
