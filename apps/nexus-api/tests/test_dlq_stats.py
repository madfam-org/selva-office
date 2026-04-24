"""Tests for the DLQ stats health endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_dlq_stats_endpoint():
    """GET /api/v1/health/dlq-stats returns DLQ depth and recent entries."""
    from nexus_api.routers.health import dlq_stats

    mock_client = AsyncMock()
    mock_client.xlen = AsyncMock(return_value=3)
    mock_client.xrevrange = AsyncMock(
        return_value=[
            ("1-0", {"data": '{"task_id": "t1"}'}),
            ("2-0", {"data": '{"task_id": "t2"}'}),
        ]
    )

    mock_pool = MagicMock()
    mock_pool.client = AsyncMock(return_value=mock_client)

    with patch("nexus_api.routers.health.get_redis_pool", return_value=mock_pool):
        result = await dlq_stats()

    assert result["depth"] == 3
    assert len(result["recent"]) == 2


@pytest.mark.asyncio
async def test_dlq_stats_handles_redis_error():
    """DLQ stats returns graceful error when Redis is unavailable."""
    from nexus_api.routers.health import dlq_stats

    mock_pool = MagicMock()
    mock_pool.client = AsyncMock(side_effect=ConnectionError("no redis"))

    with patch("nexus_api.routers.health.get_redis_pool", return_value=mock_pool):
        result = await dlq_stats()

    assert "error" in result
