"""Tests for OpenTelemetry tracing initialization."""

from __future__ import annotations

import builtins
import os
from unittest.mock import MagicMock, patch

from selva_observability.tracing import init_tracing


class TestInitTracing:
    """init_tracing() follows the same env-gated no-op pattern as init_sentry()."""

    def test_noop_without_env(self) -> None:
        """init_tracing is a no-op when OTEL_EXPORTER_OTLP_ENDPOINT is not set."""
        env = dict(os.environ)
        env.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        with patch.dict("os.environ", env, clear=True):
            # Should not raise
            init_tracing("test-service")

    def test_noop_when_packages_missing(self) -> None:
        """init_tracing warns when OTel packages are not installed."""
        real_import = builtins.__import__

        def _block_otel(name: str, *args: object, **kwargs: object) -> object:
            if name.startswith("opentelemetry"):
                raise ImportError(f"No module named '{name}'")
            return real_import(name, *args, **kwargs)

        with (
            patch.dict(
                "os.environ",
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
            ),
            patch("builtins.__import__", side_effect=_block_otel),
        ):
            # Should not raise
            init_tracing("test-service")

    def test_configures_provider_http(self) -> None:
        """init_tracing configures TracerProvider when env is set (http endpoint)."""
        mock_trace_module = MagicMock()
        # Ensure ``from opentelemetry import trace`` resolves to mock_trace_module
        # (MagicMock auto-creates child attributes, so we must set this explicitly).
        mock_trace_module.trace = mock_trace_module
        mock_tracer_provider_cls = MagicMock()
        mock_batch_processor_cls = MagicMock()
        mock_resource_cls = MagicMock()
        mock_exporter_cls = MagicMock()

        modules = {
            "opentelemetry": mock_trace_module,
            "opentelemetry.trace": mock_trace_module,
            "opentelemetry.sdk.trace": MagicMock(TracerProvider=mock_tracer_provider_cls),
            "opentelemetry.sdk.trace.export": MagicMock(
                BatchSpanProcessor=mock_batch_processor_cls
            ),
            "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource_cls),
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(
                OTLPSpanExporter=mock_exporter_cls
            ),
        }
        with (
            patch.dict(
                "os.environ",
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
            ),
            patch.dict("sys.modules", modules),
        ):
            init_tracing("test-service")

        # Verify TracerProvider was instantiated
        mock_tracer_provider_cls.assert_called_once()
        # Verify exporter was created with insecure=True for http
        mock_exporter_cls.assert_called_once_with(
            endpoint="http://localhost:4317", insecure=True
        )
        # Verify set_tracer_provider was called
        mock_trace_module.set_tracer_provider.assert_called_once()

    def test_configures_secure_for_https(self) -> None:
        """init_tracing sets insecure=False for https endpoints."""
        mock_trace_module = MagicMock()
        mock_exporter_cls = MagicMock()

        modules = {
            "opentelemetry": mock_trace_module,
            "opentelemetry.trace": mock_trace_module,
            "opentelemetry.sdk.trace": MagicMock(TracerProvider=MagicMock()),
            "opentelemetry.sdk.trace.export": MagicMock(BatchSpanProcessor=MagicMock()),
            "opentelemetry.sdk.resources": MagicMock(Resource=MagicMock()),
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(
                OTLPSpanExporter=mock_exporter_cls
            ),
        }
        with (
            patch.dict(
                "os.environ",
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "https://otel.example.com:4317"},
            ),
            patch.dict("sys.modules", modules),
        ):
            init_tracing("secure-service")

        mock_exporter_cls.assert_called_once_with(
            endpoint="https://otel.example.com:4317", insecure=False
        )

    def test_resource_contains_service_name(self) -> None:
        """init_tracing creates a Resource with the correct service.name."""
        mock_resource_cls = MagicMock()

        modules = {
            "opentelemetry": MagicMock(),
            "opentelemetry.trace": MagicMock(),
            "opentelemetry.sdk.trace": MagicMock(TracerProvider=MagicMock()),
            "opentelemetry.sdk.trace.export": MagicMock(BatchSpanProcessor=MagicMock()),
            "opentelemetry.sdk.resources": MagicMock(Resource=mock_resource_cls),
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": MagicMock(
                OTLPSpanExporter=MagicMock()
            ),
        }
        with (
            patch.dict(
                "os.environ",
                {"OTEL_EXPORTER_OTLP_ENDPOINT": "http://localhost:4317"},
            ),
            patch.dict("sys.modules", modules),
        ):
            init_tracing("my-api")

        mock_resource_cls.create.assert_called_once_with({"service.name": "my-api"})
