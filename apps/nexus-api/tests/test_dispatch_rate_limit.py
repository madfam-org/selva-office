"""Tests for per-user dispatch rate limiting."""

from __future__ import annotations

import time

from nexus_api.ws import MessageRateLimiter


def test_allows_under_limit():
    """Requests under the limit should be allowed."""
    limiter = MessageRateLimiter(max_messages=5, window_seconds=60.0)
    for _ in range(5):
        assert limiter.check("user-1") is True


def test_blocks_over_limit_returns_429():
    """Requests over the limit should be rejected."""
    limiter = MessageRateLimiter(max_messages=3, window_seconds=60.0)
    for _ in range(3):
        assert limiter.check("user-1") is True
    # 4th request should be blocked
    assert limiter.check("user-1") is False


def test_per_user_isolation():
    """Different users have independent rate limits."""
    limiter = MessageRateLimiter(max_messages=2, window_seconds=60.0)
    # User A uses both slots
    assert limiter.check("user-a") is True
    assert limiter.check("user-a") is True
    assert limiter.check("user-a") is False  # blocked

    # User B should still be allowed
    assert limiter.check("user-b") is True
    assert limiter.check("user-b") is True


def test_window_expiry():
    """Requests should be allowed again after the window expires."""
    limiter = MessageRateLimiter(max_messages=1, window_seconds=0.1)
    assert limiter.check("user-1") is True
    assert limiter.check("user-1") is False  # blocked
    time.sleep(0.15)
    assert limiter.check("user-1") is True  # window expired
