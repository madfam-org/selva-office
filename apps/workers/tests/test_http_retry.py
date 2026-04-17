"""Tests for fire-and-forget HTTP retry utility and circuit breaker."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset_circuit_state() -> None:
    """Clear module-level circuit breaker state between tests."""
    from selva_workers.http_retry import _circuit_state

    _circuit_state.clear()


@pytest.fixture(autouse=True)
def _clean_circuits() -> None:  # type: ignore[misc]
    """Reset circuit breakers before each test."""
    _reset_circuit_state()


def _mock_response(status_code: int = 200, text: str = "OK") -> MagicMock:
    return MagicMock(status_code=status_code, text=text)


def _make_async_client(
    response: MagicMock | None = None, exc: Exception | None = None,
) -> MagicMock:
    """Create a mock httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    if exc:
        mock_client.request.side_effect = exc
    else:
        mock_client.request.return_value = response or _mock_response()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


# ---------------------------------------------------------------------------
# fire_and_forget_request tests
# ---------------------------------------------------------------------------


class TestFireAndForgetRequest:
    """fire_and_forget_request sends HTTP requests with retry and circuit breaker."""

    @pytest.mark.asyncio
    async def test_successful_request_returns_true(self) -> None:
        mock_client = _make_async_client(_mock_response(200))

        with patch(
            "selva_workers.http_retry.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from selva_workers.http_retry import fire_and_forget_request

            result = await fire_and_forget_request(
                "PATCH", "http://test:4300/api/v1/tasks/1", json={"status": "running"}
            )

        assert result is True
        mock_client.request.assert_called_once_with(
            "PATCH", "http://test:4300/api/v1/tasks/1", json={"status": "running"},
            headers=None,
        )

    @pytest.mark.asyncio
    async def test_201_returns_true(self) -> None:
        mock_client = _make_async_client(_mock_response(201))

        with patch(
            "selva_workers.http_retry.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from selva_workers.http_retry import fire_and_forget_request

            result = await fire_and_forget_request("POST", "http://test:4300/api/v1/events")

        assert result is True

    @pytest.mark.asyncio
    async def test_400_returns_false_without_retry(self) -> None:
        mock_client = _make_async_client(_mock_response(400, "Bad request"))

        with patch(
            "selva_workers.http_retry.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from selva_workers.http_retry import fire_and_forget_request

            result = await fire_and_forget_request("PATCH", "http://test:4300/api/v1/tasks/1")

        assert result is False
        # 4xx should not be retried -- only one call.
        mock_client.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_retries_on_500(self) -> None:
        """Retries on 5xx, succeeds on third attempt."""
        responses = [
            _mock_response(500, "Internal Server Error"),
            _mock_response(502, "Bad Gateway"),
            _mock_response(200, "OK"),
        ]
        mock_client = AsyncMock()
        mock_client.request.side_effect = responses
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "selva_workers.http_retry.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("selva_workers.http_retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            from selva_workers.http_retry import fire_and_forget_request

            result = await fire_and_forget_request(
                "POST",
                "http://test:4300/api/v1/events",
                json={"event_type": "test"},
                max_retries=3,
            )

        assert result is True
        assert mock_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_returns_false_after_max_retries(self) -> None:
        mock_client = _make_async_client(exc=ConnectionError("refused"))

        with (
            patch(
                "selva_workers.http_retry.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("selva_workers.http_retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            from selva_workers.http_retry import fire_and_forget_request

            result = await fire_and_forget_request(
                "PATCH",
                "http://test:4300/api/v1/tasks/1",
                max_retries=3,
            )

        assert result is False
        assert mock_client.request.call_count == 3

    @pytest.mark.asyncio
    async def test_never_raises(self) -> None:
        mock_client = _make_async_client(exc=RuntimeError("something terrible"))

        with (
            patch(
                "selva_workers.http_retry.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("selva_workers.http_retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            from selva_workers.http_retry import fire_and_forget_request

            # Should not raise.
            result = await fire_and_forget_request(
                "POST", "http://test:4300/api/v1/events", max_retries=2
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_exponential_backoff_delays(self) -> None:
        mock_client = _make_async_client(exc=ConnectionError("refused"))

        with (
            patch(
                "selva_workers.http_retry.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch(
                "selva_workers.http_retry.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            from selva_workers.http_retry import fire_and_forget_request

            await fire_and_forget_request(
                "PATCH",
                "http://test:4300/api/v1/tasks/1",
                max_retries=4,
                base_delay=1.0,
            )

        # Delays: 1.0 * 2^0 = 1.0, 1.0 * 2^1 = 2.0, 1.0 * 2^2 = 4.0
        # (no sleep after the last attempt)
        assert mock_sleep.call_count == 3
        delays = [call.args[0] for call in mock_sleep.call_args_list]
        assert delays == [1.0, 2.0, 4.0]

    @pytest.mark.asyncio
    async def test_custom_timeout_passed_to_client(self) -> None:
        mock_client = _make_async_client(_mock_response(200))

        with patch(
            "selva_workers.http_retry.httpx.AsyncClient",
            return_value=mock_client,
        ) as mock_cls:
            from selva_workers.http_retry import fire_and_forget_request

            await fire_and_forget_request(
                "POST", "http://test:4300/api/v1/events", timeout=2.0
            )

        mock_cls.assert_called_once_with(timeout=2.0)

    @pytest.mark.asyncio
    async def test_passes_json_body(self) -> None:
        mock_client = _make_async_client(_mock_response(200))

        with patch(
            "selva_workers.http_retry.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from selva_workers.http_retry import fire_and_forget_request

            await fire_and_forget_request(
                "POST",
                "http://test:4300/api/v1/events",
                json={"event_type": "task.started", "task_id": "t1"},
            )

        call_kwargs = mock_client.request.call_args
        assert call_kwargs.kwargs["json"] == {
            "event_type": "task.started",
            "task_id": "t1",
        }


# ---------------------------------------------------------------------------
# Circuit breaker tests
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    """_CircuitBreaker tracks failures and opens after threshold."""

    def test_initially_closed(self) -> None:
        from selva_workers.http_retry import _CircuitBreaker

        cb = _CircuitBreaker(threshold=3)
        assert cb.is_open() is False

    def test_opens_after_threshold_failures(self) -> None:
        from selva_workers.http_retry import _CircuitBreaker

        cb = _CircuitBreaker(threshold=3, window=60.0, cooldown=10.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open() is False
        cb.record_failure()  # 3rd failure -> opens
        assert cb.is_open() is True

    def test_resets_on_success(self) -> None:
        from selva_workers.http_retry import _CircuitBreaker

        cb = _CircuitBreaker(threshold=3, window=60.0, cooldown=10.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.is_open() is False
        # After reset, need threshold failures again to open.
        cb.record_failure()
        assert cb.is_open() is False

    def test_closes_after_cooldown(self) -> None:
        from selva_workers.http_retry import _CircuitBreaker

        cb = _CircuitBreaker(threshold=2, window=60.0, cooldown=0.0)
        cb.record_failure()
        cb.record_failure()
        # Cooldown is 0, so it should already be past the open_until time.
        # Force the _open_until to be in the past.
        cb._open_until = time.monotonic() - 1.0
        assert cb.is_open() is False

    def test_purges_old_failures_outside_window(self) -> None:
        from selva_workers.http_retry import _CircuitBreaker

        cb = _CircuitBreaker(threshold=3, window=0.0, cooldown=10.0)
        # With window=0, all failures are "old" by the time we check.
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        # The window is 0s, so failures are purged during record_failure.
        # Only the latest one survives, so threshold is not reached.
        # However, record_failure appends then purges, so with window=0
        # all but the just-appended one get purged.
        # With 3 calls, each call appends and immediately purges the old ones.
        # After 3 rapid calls with window=0, only 1 survives (the latest).
        assert cb.is_open() is False

    @pytest.mark.asyncio
    async def test_skips_request_when_circuit_open(self) -> None:
        """fire_and_forget_request returns False immediately when circuit is open."""
        from selva_workers.http_retry import _circuit_state, _CircuitBreaker

        # Pre-populate an open circuit breaker for the target host.
        cb = _CircuitBreaker(threshold=1, cooldown=60.0)
        cb.record_failure()  # Opens the circuit.
        _circuit_state["http://test:4300"] = cb

        with patch(
            "selva_workers.http_retry.httpx.AsyncClient",
        ) as mock_cls:
            from selva_workers.http_retry import fire_and_forget_request

            result = await fire_and_forget_request(
                "PATCH", "http://test:4300/api/v1/tasks/1"
            )

        assert result is False
        # httpx.AsyncClient should not be instantiated at all.
        mock_cls.assert_not_called()

    def test_separate_circuits_per_host(self) -> None:
        from selva_workers.http_retry import _get_circuit_breaker

        cb_a = _get_circuit_breaker("http://host-a:4300/api/v1/tasks")
        cb_b = _get_circuit_breaker("http://host-b:4300/api/v1/tasks")

        assert cb_a is not cb_b

        # Same host, different path -> same circuit.
        cb_a2 = _get_circuit_breaker("http://host-a:4300/api/v1/events")
        assert cb_a is cb_a2


# ---------------------------------------------------------------------------
# Integration: retry + circuit breaker interaction
# ---------------------------------------------------------------------------


class TestRetryCircuitIntegration:
    """Verify that retries record failures to the circuit breaker."""

    @pytest.mark.asyncio
    async def test_repeated_failures_open_circuit(self) -> None:
        """After enough failures across multiple calls, the circuit opens."""
        from selva_workers.http_retry import _get_circuit_breaker

        mock_client = _make_async_client(exc=ConnectionError("refused"))

        with (
            patch(
                "selva_workers.http_retry.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("selva_workers.http_retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            from selva_workers.http_retry import fire_and_forget_request

            # 3 retries per call = 3 failures recorded.
            await fire_and_forget_request(
                "POST", "http://test:4300/api/v1/events", max_retries=3
            )
            # Another call: 2 more failures -> 5 total -> circuit opens.
            await fire_and_forget_request(
                "POST", "http://test:4300/api/v1/events", max_retries=2
            )

        cb = _get_circuit_breaker("http://test:4300/api/v1/events")
        assert cb.is_open() is True

    @pytest.mark.asyncio
    async def test_success_resets_circuit_after_failures(self) -> None:
        from selva_workers.http_retry import _get_circuit_breaker

        responses = [
            ConnectionError("refused"),
            ConnectionError("refused"),
            _mock_response(200),  # success on third try
        ]
        mock_client = AsyncMock()
        mock_client.request.side_effect = responses
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "selva_workers.http_retry.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("selva_workers.http_retry.asyncio.sleep", new_callable=AsyncMock),
        ):
            from selva_workers.http_retry import fire_and_forget_request

            result = await fire_and_forget_request(
                "POST", "http://test:4300/api/v1/events", max_retries=3
            )

        assert result is True
        cb = _get_circuit_breaker("http://test:4300/api/v1/events")
        assert cb.is_open() is False
