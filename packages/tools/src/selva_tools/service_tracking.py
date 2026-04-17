"""Lightweight service consumption tracking.

Emits usage events to the event stream via nexus-api.
Does not block tool execution — fire-and-forget.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def emit_service_usage(
    service: str,
    action: str,
    amount: int = 1,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record service usage for consumption tracking.

    Posts a ``service_call`` event to nexus-api.  Errors are logged at
    debug level and never raised — callers should treat this as optional
    telemetry.
    """
    try:
        import httpx

        nexus_url = os.environ.get("NEXUS_API_URL", "")
        worker_token = os.environ.get("WORKER_API_TOKEN", "")
        if not nexus_url or not worker_token:
            return

        httpx.post(
            f"{nexus_url}/api/v1/events",
            json={
                "event_type": "service_call",
                "event_category": "external_service",
                "provider": service,
                "model": action,
                "token_count": amount,
                "payload": metadata or {},
            },
            headers={"Authorization": f"Bearer {worker_token}"},
            timeout=2.0,
        )
    except Exception:
        logger.debug("Service usage tracking failed", exc_info=True)
