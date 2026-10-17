"""Structured JSON logging via structlog with service context."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from selva_observability.redaction import redact_credentials_processor


def configure_logging(
    service_name: str = "unknown",
    log_format: str | None = None,
    log_level: str | None = None,
) -> None:
    """Set up structlog with JSON or console rendering.

    Reads LOG_FORMAT and LOG_LEVEL from environment if not provided.
    """
    fmt = log_format or os.environ.get("LOG_FORMAT", "json")
    level_name = log_level or os.environ.get("LOG_LEVEL", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _add_service_name(service_name),
    ]

    if fmt == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # The formatter chain runs for BOTH structlog-native events and stdlib
    # ``logging`` records, so credential redaction lives here (defense in
    # depth behind call-site ``redact_url``). ``format_exc_info`` renders a
    # stdlib record's exc_info to text first, so exception messages that embed
    # a DSN (e.g. a URL parse error) are redacted too; it is a no-op for
    # structlog-native events, which already ran it in ``shared_processors``.
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.format_exc_info,
            redact_credentials_processor,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)


def _add_service_name(service_name: str) -> structlog.types.Processor:
    """Create a processor that adds service_name to each log event."""

    def processor(
        logger: Any,
        method_name: str,
        event_dict: MutableMapping[str, Any],
    ) -> MutableMapping[str, Any]:
        event_dict["service"] = service_name
        return event_dict

    return processor


def bind_task_context(
    task_id: str,
    agent_id: str | None = None,
    request_id: str | None = None,
) -> None:
    """Bind task-scoped context variables for structured logging."""
    ctx: dict[str, str] = {"task_id": task_id}
    if agent_id:
        ctx["agent_id"] = agent_id
    if request_id:
        ctx["request_id"] = request_id
    structlog.contextvars.bind_contextvars(**ctx)


def clear_context() -> None:
    """Clear all bound context variables."""
    structlog.contextvars.clear_contextvars()
