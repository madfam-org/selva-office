"""Lightweight service consumption tracking for nexus-api.

Emits events directly to the database via the events infrastructure.
Fire-and-forget — errors are logged at debug level and never raised.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def emit_proxy_usage(
    caller: str,
    provider: str,
    model: str,
    usage: dict[str, int],
    duration_ms: int,
) -> None:
    """Record an inference proxy call for consumption tracking."""
    try:
        import os

        import httpx

        nexus_url = os.environ.get("NEXUS_API_URL", "http://localhost:4300")
        worker_token = os.environ.get("WORKER_API_TOKEN", "")
        if not worker_token:
            return

        httpx.post(
            f"{nexus_url}/api/v1/events",
            json={
                "event_type": "service_call",
                "event_category": "inference_proxy",
                "provider": provider,
                "model": model,
                "token_count": usage.get("total_tokens", 0),
                "duration_ms": duration_ms,
                "payload": {
                    "caller": caller,
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                },
            },
            headers={"Authorization": f"Bearer {worker_token}"},
            timeout=2.0,
        )
    except Exception:
        logger.debug("Proxy usage tracking failed", exc_info=True)
