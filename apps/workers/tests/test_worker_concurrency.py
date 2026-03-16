"""Tests for worker concurrency and worktree cleanup."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_semaphore_limits_concurrency():
    """Verify that the semaphore caps parallel task execution."""
    import autoswarm_workers.__main__ as worker_mod
    from autoswarm_workers.__main__ import _process_with_semaphore

    counter = {"active": 0, "max_active": 0}
    original_semaphore = worker_mod._task_semaphore
    worker_mod._task_semaphore = asyncio.Semaphore(2)  # Allow 2 concurrent

    async def slow_process(task_data):
        counter["active"] += 1
        counter["max_active"] = max(counter["max_active"], counter["active"])
        await asyncio.sleep(0.1)
        counter["active"] -= 1

    consumer = AsyncMock()
    consumer.ack = AsyncMock()

    with patch.object(worker_mod, "process_task", side_effect=slow_process):
        tasks = [
            asyncio.create_task(
                _process_with_semaphore(consumer, f"msg-{i}", {"task_id": f"t-{i}"})
            )
            for i in range(5)
        ]
        await asyncio.gather(*tasks)

    assert counter["max_active"] <= 2
    assert consumer.ack.call_count == 5

    worker_mod._task_semaphore = original_semaphore


@pytest.mark.asyncio
async def test_shutdown_drains_active_tasks():
    """Verify that active tasks are drained on shutdown."""
    from autoswarm_workers.__main__ import _active_tasks

    completed = {"count": 0}

    async def slow_task():
        await asyncio.sleep(0.05)
        completed["count"] += 1

    for _ in range(3):
        task = asyncio.create_task(slow_task())
        _active_tasks.add(task)
        task.add_done_callback(_active_tasks.discard)

    await asyncio.gather(*_active_tasks, return_exceptions=True)
    assert completed["count"] == 3


@pytest.mark.asyncio
async def test_ack_on_success():
    """Verify that successful tasks are acknowledged."""
    import autoswarm_workers.__main__ as worker_mod
    from autoswarm_workers.__main__ import _process_with_semaphore

    original_semaphore = worker_mod._task_semaphore
    worker_mod._task_semaphore = asyncio.Semaphore(1)

    consumer = AsyncMock()
    consumer.ack = AsyncMock()

    with patch.object(worker_mod, "process_task", new_callable=AsyncMock):
        await _process_with_semaphore(consumer, "msg-1", {"task_id": "t-1"})

    consumer.ack.assert_awaited_once_with("msg-1")
    worker_mod._task_semaphore = original_semaphore


@pytest.mark.asyncio
async def test_dlq_on_max_retries_concurrent():
    """Verify that tasks are moved to DLQ after max retries."""
    import autoswarm_workers.__main__ as worker_mod
    from autoswarm_workers.__main__ import _process_with_semaphore

    original_semaphore = worker_mod._task_semaphore
    worker_mod._task_semaphore = asyncio.Semaphore(1)

    consumer = AsyncMock()
    consumer.retry_count = AsyncMock(return_value=3)
    consumer.move_to_dlq = AsyncMock()

    with patch.object(worker_mod, "process_task", side_effect=RuntimeError("boom")):
        await _process_with_semaphore(consumer, "msg-1", {"task_id": "t-1"})

    consumer.move_to_dlq.assert_awaited_once()
    worker_mod._task_semaphore = original_semaphore


@pytest.mark.asyncio
async def test_removes_stale_worktrees(tmp_path):
    """Verify that worktrees older than stale_hours are removed."""
    from autoswarm_workers.__main__ import _cleanup_stale_worktrees

    # Create a repo with _worktrees
    repo = tmp_path / "my-repo"
    wt_root = repo / "_worktrees"
    stale_wt = wt_root / "old-branch"
    stale_wt.mkdir(parents=True)

    # Set mtime to 25 hours ago
    old_time = time.time() - (25 * 3600)
    import os
    os.utime(stale_wt, (old_time, old_time))

    removed = await _cleanup_stale_worktrees(str(tmp_path), stale_hours=24)
    assert removed == 1
    assert not stale_wt.exists()


@pytest.mark.asyncio
async def test_preserves_fresh_worktrees(tmp_path):
    """Verify that recent worktrees are not removed."""
    from autoswarm_workers.__main__ import _cleanup_stale_worktrees

    repo = tmp_path / "my-repo"
    wt_root = repo / "_worktrees"
    fresh_wt = wt_root / "new-branch"
    fresh_wt.mkdir(parents=True)
    # mtime is now (fresh), should not be removed

    removed = await _cleanup_stale_worktrees(str(tmp_path), stale_hours=24)
    assert removed == 0
    assert fresh_wt.exists()


@pytest.mark.asyncio
async def test_handles_missing_base_dir():
    """Verify graceful handling of nonexistent base directory."""
    from autoswarm_workers.__main__ import _cleanup_stale_worktrees

    removed = await _cleanup_stale_worktrees("/nonexistent/path", stale_hours=24)
    assert removed == 0
