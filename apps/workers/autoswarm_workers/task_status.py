"""Task status updates -- PATCH task lifecycle to nexus-api."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def update_task_status(
    nexus_url: str,
    task_id: str,
    status: str,
    result: dict | None = None,
    started_at: str | None = None,
    error_message: str | None = None,
) -> None:
    """PATCH task status to the nexus-api.

    Fire-and-forget: failures are logged but never raised, matching the
    same resilience pattern used by ``metering.py``.
    """
    if task_id == "unknown":
        return
    body: dict = {"status": status}
    if result is not None:
        body["result"] = result
    if started_at is not None:
        body["started_at"] = started_at
    if error_message is not None:
        body["error_message"] = error_message
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.patch(
                f"{nexus_url}/api/v1/swarms/tasks/{task_id}",
                json=body,
            )
            if resp.status_code not in (200, 204):
                logger.warning(
                    "Task status update rejected (status %d): %s",
                    resp.status_code,
                    resp.text,
                )
    except Exception:
        logger.warning("Failed to update task %s status to %s", task_id, status, exc_info=True)
