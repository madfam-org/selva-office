"""Tests for the optional OTel span wrapper in Redis pool."""

from __future__ import annotations

import builtins
from unittest.mock import MagicMock, patch

from selva_redis_pool.pool import _redis_span


class TestRedisSpan:
    """_redis_span() is a no-op when OTel is not installed."""

    def test_noop_without_opentelemetry(self) -> None:
        """When opentelemetry is not importable, _redis_span yields without error."""
        real_import = builtins.__import__

        def _block_otel(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("opentelemetry"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with (
            patch("builtins.__import__", side_effect=_block_otel),
            _redis_span("get"),
        ):
            pass  # Should not raise

    def test_creates_span_when_available(self) -> None:
        """When opentelemetry is available, _redis_span creates a span."""
        mock_trace_mod = MagicMock()
        mock_tracer = MagicMock()
        mock_trace_mod.get_tracer.return_value = mock_tracer
        # Make ``from opentelemetry import trace`` resolve correctly
        mock_trace_mod.trace = mock_trace_mod

        modules = {
            "opentelemetry": mock_trace_mod,
            "opentelemetry.trace": mock_trace_mod,
        }
        with patch.dict("sys.modules", modules), _redis_span("set"):
            pass  # Should not raise
