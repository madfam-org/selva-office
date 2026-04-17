"""Tests for the FinancialCircuitBreaker daily exposure limiter.

Covers:
- check() within/at/over limit
- record() atomic increment
- get_status() response structure
- Fail-safe behaviour when Redis is unavailable
- TTL handling on first-write-of-day
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from selva_orchestrator.circuit_breaker import (
    DEFAULT_DAILY_LIMIT_CENTS,
    FinancialCircuitBreaker,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_redis() -> MagicMock:
    """Return a mock Redis client with standard async methods."""
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    redis.incrby = AsyncMock(return_value=0)
    redis.ttl = AsyncMock(return_value=-1)
    redis.expire = AsyncMock(return_value=True)
    return redis


@pytest.fixture()
def breaker(mock_redis: MagicMock) -> FinancialCircuitBreaker:
    """Return a breaker with default $50.00 daily limit."""
    return FinancialCircuitBreaker(mock_redis)


@pytest.fixture()
def small_breaker(mock_redis: MagicMock) -> FinancialCircuitBreaker:
    """Return a breaker with a small $5.00 daily limit."""
    return FinancialCircuitBreaker(mock_redis, daily_limit_cents=500)


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------


class TestDefaults:
    """Verify default values match the Manifesto."""

    def test_default_daily_limit_is_fifty_dollars(self) -> None:
        assert DEFAULT_DAILY_LIMIT_CENTS == 5000

    def test_custom_limit(self, small_breaker: FinancialCircuitBreaker) -> None:
        assert small_breaker._daily_limit_cents == 500


# ---------------------------------------------------------------------------
# check()
# ---------------------------------------------------------------------------


class TestCheck:
    """check() returns True when amount is within limit, False otherwise."""

    @pytest.mark.asyncio()
    async def test_check_within_limit(self, breaker: FinancialCircuitBreaker) -> None:
        """Zero existing exposure + small request = allowed."""
        assert await breaker.check("org-1", 100) is True

    @pytest.mark.asyncio()
    async def test_check_at_limit(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        """Exactly at limit = still allowed."""
        mock_redis.get = AsyncMock(return_value="4900")
        assert await breaker.check("org-1", 100) is True

    @pytest.mark.asyncio()
    async def test_check_over_limit(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        """Over limit = denied."""
        mock_redis.get = AsyncMock(return_value="4901")
        assert await breaker.check("org-1", 100) is False

    @pytest.mark.asyncio()
    async def test_check_already_at_limit(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        """Already at the daily limit = even 1 cent is denied."""
        mock_redis.get = AsyncMock(return_value="5000")
        assert await breaker.check("org-1", 1) is False

    @pytest.mark.asyncio()
    async def test_check_with_no_existing_balance(self, breaker: FinancialCircuitBreaker) -> None:
        """No Redis key (first usage of the day) = allowed."""
        assert await breaker.check("org-1", 5000) is True

    @pytest.mark.asyncio()
    async def test_check_zero_amount(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        """Zero amount check is always within limit."""
        mock_redis.get = AsyncMock(return_value="5000")
        assert await breaker.check("org-1", 0) is True


# ---------------------------------------------------------------------------
# check() fail-safe
# ---------------------------------------------------------------------------


class TestCheckFailSafe:
    """When Redis is unavailable, check() denies (fail-safe)."""

    @pytest.mark.asyncio()
    async def test_redis_error_denies(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        assert await breaker.check("org-1", 100) is False


# ---------------------------------------------------------------------------
# record()
# ---------------------------------------------------------------------------


class TestRecord:
    """record() atomically increments the counter and sets TTL."""

    @pytest.mark.asyncio()
    async def test_record_returns_new_total(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.incrby = AsyncMock(return_value=200)
        mock_redis.ttl = AsyncMock(return_value=3600)  # TTL already set
        total = await breaker.record("org-1", 200)
        assert total == 200
        mock_redis.incrby.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_record_sets_ttl_on_first_write(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.incrby = AsyncMock(return_value=100)
        mock_redis.ttl = AsyncMock(return_value=-1)  # No TTL = first write
        await breaker.record("org-1", 100)
        mock_redis.expire.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_record_skips_ttl_when_already_set(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.incrby = AsyncMock(return_value=300)
        mock_redis.ttl = AsyncMock(return_value=43200)  # 12h remaining
        await breaker.record("org-1", 100)
        mock_redis.expire.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_record_redis_error_returns_zero(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.incrby = AsyncMock(side_effect=ConnectionError("Redis down"))
        total = await breaker.record("org-1", 100)
        assert total == 0


# ---------------------------------------------------------------------------
# get_status()
# ---------------------------------------------------------------------------


class TestGetStatus:
    """get_status() returns a summary dict with usage info."""

    @pytest.mark.asyncio()
    async def test_status_structure(self, breaker: FinancialCircuitBreaker) -> None:
        status = await breaker.get_status("org-1")
        assert "org_id" in status
        assert "used_cents" in status
        assert "remaining_cents" in status
        assert "limit_cents" in status
        assert "tripped" in status
        assert "resets_at" in status

    @pytest.mark.asyncio()
    async def test_status_empty_usage(self, breaker: FinancialCircuitBreaker) -> None:
        status = await breaker.get_status("org-1")
        assert status["used_cents"] == 0
        assert status["remaining_cents"] == 5000
        assert status["tripped"] is False

    @pytest.mark.asyncio()
    async def test_status_partial_usage(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.get = AsyncMock(return_value="2000")
        status = await breaker.get_status("org-1")
        assert status["used_cents"] == 2000
        assert status["remaining_cents"] == 3000
        assert status["tripped"] is False

    @pytest.mark.asyncio()
    async def test_status_tripped(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.get = AsyncMock(return_value="5000")
        status = await breaker.get_status("org-1")
        assert status["tripped"] is True
        assert status["remaining_cents"] == 0

    @pytest.mark.asyncio()
    async def test_status_redis_error(self, breaker: FinancialCircuitBreaker, mock_redis: MagicMock) -> None:
        mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
        status = await breaker.get_status("org-1")
        assert status["tripped"] is True  # fail-safe
        assert "error" in status


# ---------------------------------------------------------------------------
# Key format
# ---------------------------------------------------------------------------


class TestKeyFormat:
    """The Redis key includes the org ID and current UTC date."""

    def test_key_contains_org_id(self, breaker: FinancialCircuitBreaker) -> None:
        key = breaker._key("madfam-org")
        assert "madfam-org" in key

    def test_key_contains_date(self, breaker: FinancialCircuitBreaker) -> None:
        key = breaker._key("org-1")
        # Key format: circuit:financial:org-1:YYYY-MM-DD
        parts = key.split(":")
        assert parts[0] == "circuit"
        assert parts[1] == "financial"
        assert len(parts[3]) == 10  # date string YYYY-MM-DD

    def test_different_orgs_different_keys(self, breaker: FinancialCircuitBreaker) -> None:
        key_a = breaker._key("org-alpha")
        key_b = breaker._key("org-beta")
        assert key_a != key_b
