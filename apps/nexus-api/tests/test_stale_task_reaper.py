"""Tests for stale task reaper endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_reaps_old_queued_tasks():
    """Tasks queued for more than 1 hour are auto-failed."""
    from nexus_api.routers.swarms import reap_stale_tasks

    old_task = MagicMock()
    old_task.id = uuid.uuid4()
    old_task.status = "queued"
    old_task.created_at = datetime.now(UTC) - timedelta(hours=2)
    old_task.error_message = None
    old_task.completed_at = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [old_task]

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()

    result = await reap_stale_tasks(db=db)

    assert result["reaped"] == 1
    assert old_task.status == "failed"
    assert old_task.error_message == "Reaped: stale task older than 1 hour"


@pytest.mark.asyncio
async def test_preserves_running_tasks():
    """Running tasks should not be reaped."""
    from nexus_api.routers.swarms import reap_stale_tasks

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()

    result = await reap_stale_tasks(db=db)
    assert result["reaped"] == 0
