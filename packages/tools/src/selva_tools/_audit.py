"""Fire-and-forget audit-event emitter for secret-access operations.

Closes ECOSYSTEM_AUDIT_20260417.md §4.3 audit-trail gap: the Vault
tools (store / retrieve / delete / rotate) previously logged to stdout
only, meaning a centralised "who accessed which secret when" query
required scraping K8s logs. After this change, every secret access
emits a structured ``TaskEvent`` to ``POST /api/v1/events/`` so the
nexus-api's existing observability stack (which already powers the
Selva dashboard + /api/v1/events/ws websocket) has a queryable record.

Design:
  - Fire-and-forget: a failed audit emission NEVER fails the underlying
    tool call. The Vault tool must succeed even if nexus-api is down.
  - Tiny dependency footprint: httpx only. No selva_workers import
    (that would create a circular dep with the tools package).
  - Never includes the secret value, not even masked. Only metadata:
    key, namespace, operation, success, optional agent_id + correlation.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_NEXUS_API_URL_ENV = "NEXUS_API_URL"
_WORKER_TOKEN_ENV = "WORKER_API_TOKEN"
_AGENT_ID_ENV = "SELVA_AGENT_ID"  # Workers set this; absent elsewhere.


def _headers() -> dict[str, str]:
    token = os.environ.get(_WORKER_TOKEN_ENV, "dev-bypass")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def emit_secret_access_event(
    *,
    operation: str,
    key: str,
    namespace: str,
    success: bool,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Post a ``secret_<operation>`` TaskEvent to nexus-api, fire-and-forget.

    Arguments:
        operation:   "read" | "write" | "delete" | "rotate" | "list"
        key:         Secret key name (NEVER the value).
        namespace:   K8s namespace / vault namespace.
        success:     True if the underlying Vault op succeeded.
        error_message: Short error description on failure. Truncated.
        extra:       Optional metadata (e.g. correlation IDs). Treated
                     as opaque payload by the event pipeline.
    """
    nexus_url = os.environ.get(_NEXUS_API_URL_ENV, "")
    if not nexus_url:
        logger.debug("audit: NEXUS_API_URL not set — skipping secret-access event")
        return

    body: dict[str, Any] = {
        "event_type": f"secret_{operation}",
        "event_category": "secret_management",
        "agent_id": os.environ.get(_AGENT_ID_ENV) or None,
        "payload": {
            "key": key,
            "namespace": namespace,
            "success": success,
        },
    }
    if error_message:
        body["error_message"] = str(error_message)[:500]
    if extra:
        body["payload"].update(extra)

    try:
        async with httpx.AsyncClient(timeout=2.0) as http:
            await http.post(
                f"{nexus_url.rstrip('/')}/api/v1/events/",
                json=body,
                headers=_headers(),
            )
    except Exception as exc:  # noqa: BLE001 — audit must never surface
        logger.warning(
            "audit: secret_%s event emission failed (%s: %s)",
            operation,
            type(exc).__name__,
            exc,
        )


def emit_secret_access_event_sync(
    *,
    operation: str,
    key: str,
    namespace: str,
    success: bool,
    error_message: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Sync wrapper for callers outside an event loop.

    If a loop is already running, schedule the task without blocking.
    Otherwise run it to completion in a fresh loop. Either way,
    exceptions never escape (audit must not break the caller).
    """
    coro = emit_secret_access_event(
        operation=operation,
        key=key,
        namespace=namespace,
        success=success,
        error_message=error_message,
        extra=extra,
    )
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    try:
        if loop is not None and loop.is_running():
            loop.create_task(coro)
        else:
            asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001 — audit must never surface
        logger.warning(
            "audit: sync-wrapper failed to dispatch secret_%s event (%s)",
            operation,
            exc,
        )
