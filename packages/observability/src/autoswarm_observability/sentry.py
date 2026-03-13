"""Sentry error tracking initialization."""

from __future__ import annotations

import os


def init_sentry(
    service_name: str,
    dsn: str | None = None,
    traces_sample_rate: float = 0.1,
) -> None:
    """Initialize Sentry SDK if a DSN is available.

    Reads SENTRY_DSN and GIT_SHA from environment if not provided.
    Does nothing if no DSN is configured.
    """
    resolved_dsn = dsn or os.environ.get("SENTRY_DSN")
    if not resolved_dsn:
        return

    try:
        import sentry_sdk
    except ImportError:
        return

    release = os.environ.get("GIT_SHA", "unknown")

    sentry_sdk.init(
        dsn=resolved_dsn,
        traces_sample_rate=traces_sample_rate,
        release=f"{service_name}@{release}",
        environment=os.environ.get("ENVIRONMENT", "production"),
        server_name=service_name,
    )
