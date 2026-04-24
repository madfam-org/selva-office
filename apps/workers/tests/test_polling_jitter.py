"""Tests for approval polling jitter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_polling_jitter_varies_interval():
    """Verify that polling uses jitter (interval varies between calls)."""
    from selva_workers.interrupt_handler import InterruptHandler

    handler = InterruptHandler(
        nexus_api_url="http://localhost:4300",
        redis_url="redis://localhost:6379",
        default_timeout=5,
    )

    # Track sleep durations
    sleep_durations: list[float] = []

    async def mock_sleep(duration: float) -> None:
        sleep_durations.append(duration)
        # After collecting enough samples, raise TimeoutError to exit
        if len(sleep_durations) >= 5:
            raise TimeoutError("test exit")

    def _make_response() -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"id": "req-1", "status": "pending"}
        resp.raise_for_status.return_value = None
        return resp

    poll_responses = [_make_response() for _ in range(6)]

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=poll_responses)
    handler.client = mock_client

    with patch("asyncio.sleep", side_effect=mock_sleep):
        # Force polling path by making Redis fail
        with patch.object(handler, "_wait_via_redis", side_effect=ConnectionError("no redis")):
            with pytest.raises(TimeoutError, match="test exit"):
                await handler.wait_for_approval("req-1", timeout=10, poll_interval=0.5)

    # Verify jitter: not all intervals should be exactly the same
    assert len(sleep_durations) >= 3
    # With jitter factor (0.5 + random()) * 0.5, values should be in [0.25, 0.75]
    for d in sleep_durations:
        assert 0.2 <= d <= 0.8, f"Sleep duration {d} outside expected jitter range"
    # At least some variation (not all identical)
    unique = len(set(round(d, 4) for d in sleep_durations))
    assert unique > 1, "All sleep durations were identical -- no jitter applied"
