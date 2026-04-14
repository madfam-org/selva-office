"""PostHog analytics integration for AutoSwarm Nexus API."""

from __future__ import annotations

import contextlib

_client: object | None = None


def init_posthog() -> None:
    """Initialize PostHog client from centralized Settings."""
    global _client  # noqa: PLW0603
    from .config import get_settings

    settings = get_settings()
    if not settings.posthog_api_key:
        return
    try:
        import posthog

        posthog.api_key = settings.posthog_api_key
        posthog.host = settings.posthog_host
        _client = posthog
    except ImportError:
        pass


def track(distinct_id: str, event: str, properties: dict | None = None) -> None:
    """Capture a PostHog event."""
    if _client is None:
        return
    with contextlib.suppress(Exception):
        _client.capture(distinct_id, event, properties=properties or {})  # type: ignore[union-attr]


def shutdown() -> None:
    """Flush and shut down the PostHog client."""
    if _client is None:
        return
    with contextlib.suppress(Exception):
        _client.shutdown()  # type: ignore[union-attr]
