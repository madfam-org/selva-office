"""Tests for request_id middleware W3C traceparent propagation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from nexus_api.middleware.request_id import _get_current_span_context


def _build_otel_mocks(
    *,
    is_valid: bool = True,
    trace_id: int = 0,
    span_id: int = 0,
    trace_flags: int = 0,
    format_trace_id_rv: str = "",
    format_span_id_rv: str = "",
) -> dict[str, MagicMock]:
    """Build sys.modules dict that correctly mocks opentelemetry for import.

    The function under test uses ``from opentelemetry import trace`` which
    resolves to ``sys.modules["opentelemetry"].trace``.  We must set that
    attribute explicitly so the call chain works.
    """
    mock_trace_mod = MagicMock()

    # Build the span context
    mock_ctx = MagicMock()
    mock_ctx.is_valid = is_valid
    mock_ctx.trace_id = trace_id
    mock_ctx.span_id = span_id
    mock_ctx.trace_flags = trace_flags

    mock_span = MagicMock()
    mock_span.get_span_context.return_value = mock_ctx

    # The inner ``trace`` object that ``from opentelemetry import trace`` yields
    inner_trace = MagicMock()
    inner_trace.get_current_span.return_value = mock_span
    inner_trace.format_trace_id.return_value = format_trace_id_rv
    inner_trace.format_span_id.return_value = format_span_id_rv

    # Wire: ``from opentelemetry import trace`` -> inner_trace
    mock_trace_mod.trace = inner_trace

    return {
        "opentelemetry": mock_trace_mod,
        "opentelemetry.trace": inner_trace,
    }


class TestGetCurrentSpanContext:
    """_get_current_span_context() returns traceparent or None."""

    def test_returns_none_without_opentelemetry(self) -> None:
        """Returns None when opentelemetry is not installed."""
        import builtins

        real_import = builtins.__import__

        def _block_otel(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("opentelemetry"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_block_otel):
            result = _get_current_span_context()
        assert result is None

    def test_returns_none_for_invalid_span(self) -> None:
        """Returns None when the current span context is not valid."""
        modules = _build_otel_mocks(is_valid=False)

        with patch.dict("sys.modules", modules):
            result = _get_current_span_context()
        assert result is None

    def test_returns_traceparent_for_valid_span(self) -> None:
        """Returns W3C traceparent string for a valid span context."""
        modules = _build_otel_mocks(
            is_valid=True,
            trace_id=0x0AF7651916CD43DD8448EB211C80319C,
            span_id=0x00F067AA0BA902B7,
            trace_flags=1,
            format_trace_id_rv="0af7651916cd43dd8448eb211c80319c",
            format_span_id_rv="00f067aa0ba902b7",
        )

        with patch.dict("sys.modules", modules):
            result = _get_current_span_context()

        assert result == "00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01"
