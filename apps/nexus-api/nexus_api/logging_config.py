"""Structured JSON logging via shared observability package."""

from __future__ import annotations

from autoswarm_observability import configure_logging as _configure

# Re-export for backwards compatibility. The shared package handles
# LOG_LEVEL and LOG_FORMAT env vars, service_name processor, and
# JSON/console renderer selection.
SERVICE_NAME = "nexus-api"


def configure_logging(log_format: str = "json") -> None:
    """Set up structlog with JSON or console rendering."""
    _configure(service_name=SERVICE_NAME, log_format=log_format)
