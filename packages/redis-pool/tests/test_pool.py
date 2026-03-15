"""Tests for autoswarm_redis_pool.pool — RedisPool with circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as aioredis

from autoswarm_redis_pool.pool import CircuitState, RedisPool, get_redis_pool


class TestSingleton:
    """RedisPool.get_instance() is a singleton."""

    def setup_method(self) -> None:
        RedisPool.reset_instance()

    def teardown_method(self) -> None:
        RedisPool.reset_instance()

    def test_get_instance_returns_same_object(self) -> None:
        pool_a = RedisPool.get_instance(url="redis://localhost:6379")
        pool_b = RedisPool.get_instance()
        assert pool_a is pool_b

    def test_reset_instance_clears(self) -> None:
        pool_a = RedisPool.get_instance(url="redis://localhost:6379")
        RedisPool.reset_instance()
        pool_b = RedisPool.get_instance(url="redis://localhost:6379")
        assert pool_a is not pool_b

    def test_get_redis_pool_helper(self) -> None:
        pool = get_redis_pool(url="redis://localhost:6379")
        assert isinstance(pool, RedisPool)


class TestCircuitBreaker:
    """Circuit breaker transitions: closed -> open -> half-open -> closed."""

    def test_starts_closed(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        assert pool._circuit_state == CircuitState.CLOSED
        assert pool._failure_count == 0

    def test_stays_closed_below_threshold(self) -> None:
        pool = RedisPool(url="redis://fake:6379", circuit_failure_threshold=5)
        for _ in range(4):
            pool._record_failure()
        assert pool._circuit_state == CircuitState.CLOSED

    def test_opens_at_threshold(self) -> None:
        pool = RedisPool(url="redis://fake:6379", circuit_failure_threshold=3)
        for _ in range(3):
            pool._record_failure()
        assert pool._circuit_state == CircuitState.OPEN

    def test_open_raises_connection_error(self) -> None:
        pool = RedisPool(url="redis://fake:6379", circuit_failure_threshold=1)
        pool._record_failure()
        assert pool._circuit_state == CircuitState.OPEN
        with pytest.raises(ConnectionError, match="circuit breaker open"):
            pool._check_circuit()

    def test_transitions_to_half_open_after_cooldown(self) -> None:
        pool = RedisPool(
            url="redis://fake:6379",
            circuit_failure_threshold=1,
            circuit_cooldown=0.01,
        )
        pool._record_failure()
        assert pool._circuit_state == CircuitState.OPEN

        time.sleep(0.02)
        pool._check_circuit()  # Should not raise
        assert pool._circuit_state == CircuitState.HALF_OPEN

    def test_half_open_success_closes_circuit(self) -> None:
        pool = RedisPool(url="redis://fake:6379", circuit_failure_threshold=1)
        pool._record_failure()
        pool._circuit_state = CircuitState.HALF_OPEN

        pool._record_success()
        assert pool._circuit_state == CircuitState.CLOSED
        assert pool._failure_count == 0

    def test_success_in_closed_resets_failure_count(self) -> None:
        pool = RedisPool(url="redis://fake:6379", circuit_failure_threshold=5)
        pool._record_failure()
        pool._record_failure()
        pool._record_success()
        assert pool._failure_count == 0


class TestMetrics:
    """metrics() returns pool state."""

    def test_metrics_before_pool_init(self) -> None:
        pool = RedisPool(url="redis://fake:6379", max_connections=10)
        m = pool.metrics()
        assert m["active"] == 0
        assert m["available"] == 0
        assert m["max_connections"] == 10
        assert m["circuit_state"] == "closed"
        assert m["failure_count"] == 0

    def test_metrics_reflects_circuit_state(self) -> None:
        pool = RedisPool(url="redis://fake:6379", circuit_failure_threshold=1)
        pool._record_failure()
        m = pool.metrics()
        assert m["circuit_state"] == "open"
        assert m["failure_count"] == 1


class TestPing:
    """ping() checks connectivity and records success/failure."""

    @pytest.mark.asyncio
    async def test_ping_success(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(return_value=True)
        pool._client = mock_client
        pool._pool = MagicMock()  # Prevent _ensure_pool from creating real pool

        result = await pool.ping()
        assert result is True
        assert pool._failure_count == 0

    @pytest.mark.asyncio
    async def test_ping_failure(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock(side_effect=aioredis.ConnectionError("refused"))
        pool._client = mock_client
        pool._pool = MagicMock()

        result = await pool.ping()
        assert result is False
        assert pool._failure_count == 1


class TestExecuteWithRetry:
    """execute_with_retry() retries on transient failures."""

    @pytest.mark.asyncio
    async def test_success_on_first_try(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value="value")
        pool._client = mock_client
        pool._pool = MagicMock()

        result = await pool.execute_with_retry("get", "key")
        assert result == "value"
        mock_client.get.assert_called_once_with("key")

    @pytest.mark.asyncio
    async def test_retries_on_connection_error(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        mock_client = AsyncMock()
        mock_client.set = AsyncMock(
            side_effect=[aioredis.ConnectionError("fail"), "OK"]
        )
        pool._client = mock_client
        pool._pool = MagicMock()

        result = await pool.execute_with_retry(
            "set", "k", "v", max_retries=2, base_delay=0.001
        )
        assert result == "OK"
        assert mock_client.set.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=aioredis.ConnectionError("persistent")
        )
        pool._client = mock_client
        pool._pool = MagicMock()

        with pytest.raises(aioredis.ConnectionError, match="persistent"):
            await pool.execute_with_retry(
                "get", "key", max_retries=1, base_delay=0.001
            )


class TestClose:
    """close() releases resources."""

    @pytest.mark.asyncio
    async def test_close_cleans_up(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        mock_client = AsyncMock()
        mock_pool = AsyncMock()
        pool._client = mock_client
        pool._pool = mock_pool

        await pool.close()
        assert pool._client is None
        assert pool._pool is None
        mock_client.aclose.assert_called_once()
        mock_pool.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_when_not_initialized(self) -> None:
        pool = RedisPool(url="redis://fake:6379")
        # Should not raise
        await pool.close()
        assert pool._client is None
