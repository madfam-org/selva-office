"""Tests for the WebSocket MessageRateLimiter.

Covers the sliding-window rate limiter used by the events and approvals
WebSocket endpoints.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from nexus_api.ws import MessageRateLimiter


class TestMessageRateLimiter:
    """Unit tests for ``MessageRateLimiter``."""

    def test_allows_under_limit(self) -> None:
        """Messages within the budget are accepted."""
        rl = MessageRateLimiter(max_messages=5, window_seconds=60.0)
        for _ in range(5):
            assert rl.check("client-1") is True

    def test_blocks_over_limit(self) -> None:
        """The message that exceeds the budget is rejected."""
        rl = MessageRateLimiter(max_messages=5, window_seconds=60.0)
        for _ in range(5):
            rl.check("client-1")
        assert rl.check("client-1") is False
        # Still blocked on subsequent calls
        assert rl.check("client-1") is False

    def test_window_expiry(self) -> None:
        """After the window elapses, the client gets a fresh budget."""
        rl = MessageRateLimiter(max_messages=3, window_seconds=1.0)
        # Exhaust the budget
        for _ in range(3):
            rl.check("client-1")
        assert rl.check("client-1") is False

        # Simulate time advancing past the window
        base = time.monotonic()
        with patch("nexus_api.ws.time") as mock_time:
            mock_time.monotonic.return_value = base + 2.0
            # The sliding window should now be empty
            assert rl.check("client-1") is True

    def test_remove_client(self) -> None:
        """``remove()`` clears state so the client can send again."""
        rl = MessageRateLimiter(max_messages=2, window_seconds=60.0)
        rl.check("client-1")
        rl.check("client-1")
        assert rl.check("client-1") is False

        rl.remove("client-1")
        assert rl.check("client-1") is True

    def test_remove_unknown_client_is_safe(self) -> None:
        """``remove()`` does not raise when called with an unknown id."""
        rl = MessageRateLimiter()
        rl.remove("nonexistent")  # should not raise

    def test_independent_clients(self) -> None:
        """Each client_id gets its own budget."""
        rl = MessageRateLimiter(max_messages=2, window_seconds=60.0)
        rl.check("client-1")
        rl.check("client-1")
        assert rl.check("client-1") is False
        # client-2 should be unaffected
        assert rl.check("client-2") is True

    def test_default_parameters(self) -> None:
        """The default constructor allows 30 messages in a 60s window."""
        rl = MessageRateLimiter()
        for _ in range(30):
            assert rl.check("c") is True
        assert rl.check("c") is False
