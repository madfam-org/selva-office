"""Tests for selva_observability logging and sentry modules."""

from __future__ import annotations

import json
import logging
from io import StringIO
from unittest.mock import MagicMock, patch

import structlog

from selva_observability.logging import (
    bind_task_context,
    clear_context,
    configure_logging,
)
from selva_observability.sentry import init_sentry


class TestConfigureLogging:
    """configure_logging() sets up structlog with correct renderer."""

    def setup_method(self) -> None:
        """Reset structlog and root logger between tests."""
        structlog.reset_defaults()
        root = logging.getLogger()
        root.handlers.clear()

    def test_json_format_produces_json_output(self) -> None:
        configure_logging(service_name="test-svc", log_format="json", log_level="DEBUG")

        root = logging.getLogger()
        assert len(root.handlers) == 1

        buf = StringIO()
        root.handlers[0].stream = buf

        log = structlog.get_logger()
        log.info("hello", key="val")

        output = buf.getvalue().strip()
        parsed = json.loads(output)
        assert parsed["event"] == "hello"
        assert parsed["key"] == "val"
        assert parsed["service"] == "test-svc"

    def test_console_format(self) -> None:
        configure_logging(service_name="console-svc", log_format="console", log_level="INFO")

        root = logging.getLogger()
        assert len(root.handlers) == 1
        # Console renderer produces human-readable, non-JSON output
        buf = StringIO()
        root.handlers[0].stream = buf

        log = structlog.get_logger()
        log.info("console test")

        output = buf.getvalue()
        assert "console test" in output

    def test_default_reads_env(self) -> None:
        with patch.dict("os.environ", {"LOG_FORMAT": "json", "LOG_LEVEL": "WARNING"}):
            configure_logging(service_name="env-svc")

        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_level_override(self) -> None:
        configure_logging(service_name="lvl", log_level="ERROR")
        root = logging.getLogger()
        assert root.level == logging.ERROR

    def test_service_name_in_output(self) -> None:
        configure_logging(service_name="my-service", log_format="json")

        root = logging.getLogger()
        buf = StringIO()
        root.handlers[0].stream = buf

        log = structlog.get_logger()
        log.info("svc test")

        parsed = json.loads(buf.getvalue().strip())
        assert parsed["service"] == "my-service"


class TestBindTaskContext:
    """bind_task_context() and clear_context() manage contextvars."""

    def setup_method(self) -> None:
        structlog.reset_defaults()
        clear_context()

    def test_bind_task_id_only(self) -> None:
        bind_task_context(task_id="task-123")
        ctx = structlog.contextvars.get_contextvars()
        assert ctx["task_id"] == "task-123"
        assert "agent_id" not in ctx

    def test_bind_all_fields(self) -> None:
        bind_task_context(task_id="t-1", agent_id="a-2", request_id="r-3")
        ctx = structlog.contextvars.get_contextvars()
        assert ctx["task_id"] == "t-1"
        assert ctx["agent_id"] == "a-2"
        assert ctx["request_id"] == "r-3"

    def test_clear_context_removes_vars(self) -> None:
        bind_task_context(task_id="t-x")
        clear_context()
        ctx = structlog.contextvars.get_contextvars()
        assert "task_id" not in ctx


class TestInitSentry:
    """init_sentry() calls sentry_sdk.init when DSN is available."""

    def test_no_dsn_does_nothing(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            # Should not raise
            init_sentry("test-svc", dsn=None)

    def test_explicit_dsn_calls_init(self) -> None:
        mock_sdk = MagicMock()
        with patch.dict("sys.modules", {"sentry_sdk": mock_sdk}):
            init_sentry("my-svc", dsn="https://key@sentry.io/123", traces_sample_rate=0.5)
            mock_sdk.init.assert_called_once()
            call_kwargs = mock_sdk.init.call_args[1]
            assert call_kwargs["dsn"] == "https://key@sentry.io/123"
            assert call_kwargs["traces_sample_rate"] == 0.5
            assert "my-svc" in call_kwargs["release"]

    def test_env_dsn_calls_init(self) -> None:
        mock_sdk = MagicMock()
        with (
            patch.dict("os.environ", {"SENTRY_DSN": "https://env@sentry.io/456"}),
            patch.dict("sys.modules", {"sentry_sdk": mock_sdk}),
        ):
            init_sentry("env-svc")
            mock_sdk.init.assert_called_once()

    def test_missing_sentry_sdk_graceful(self) -> None:
        """When sentry_sdk is not importable, init_sentry should not raise."""
        with patch.dict("sys.modules", {"sentry_sdk": None}):
            # Simulating ImportError by making import fail
            import builtins

            real_import = builtins.__import__

            def mock_import(name: str, *args: object, **kwargs: object) -> object:
                if name == "sentry_sdk":
                    raise ImportError("No module named 'sentry_sdk'")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                # Should not raise
                init_sentry("no-sdk-svc", dsn="https://key@sentry.io/789")
