"""PhyneCRM webhook handler — receives CRM events and auto-dispatches tasks.

Maps CRM lifecycle events to SwarmTask dispatch via the playbook system.
Only dispatches if a matching enabled playbook exists for the event.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gateway/phyne-crm", tags=["gateway"])

# CRM event → internal event key mapping
EVENT_MAP = {
    "lead.hot": "crm:hot_lead",
    "lead.created": "crm:lead_created",
    "activity.overdue": "crm:support_ticket",
    "opportunity.created": "crm:opportunity_created",
}


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC-SHA256 webhook signature from PhyneCRM."""
    if not secret:
        return True  # skip verification if no secret configured
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("")
async def phyne_crm_webhook(request: Request):
    """Receive webhook events from PhyneCRM and auto-dispatch agent tasks.

    Flow:
    1. Verify HMAC signature
    2. Map CRM event to internal event key
    3. Look up matching playbook via /api/v1/playbooks/match
    4. If playbook found and enabled → dispatch SwarmTask with playbook_id
    5. If no playbook → acknowledge but don't dispatch
    """
    settings = get_settings()
    body = await request.body()

    # Verify signature
    signature = request.headers.get("X-PhyneCRM-Signature", "")
    webhook_secret = getattr(settings, "phyne_crm_webhook_secret", "")
    if webhook_secret and not _verify_signature(body, signature, webhook_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("event", "")
    data = payload.get("data", {})

    logger.info("PhyneCRM webhook received: event=%s", event_type)

    # Map to internal event key
    internal_event = EVENT_MAP.get(event_type)
    if not internal_event:
        return {"status": "ok", "event": event_type, "ignored": True}

    # Look up matching playbook
    from .playbooks import _playbooks

    matching_playbook = None
    for pb in _playbooks.values():
        if pb["trigger_event"] == internal_event and pb["enabled"] and not pb["require_approval"]:
            matching_playbook = pb
            break

    if not matching_playbook:
        logger.info("No matching playbook for CRM event %s (%s), skipping dispatch", event_type, internal_event)
        return {"status": "ok", "event": event_type, "no_playbook": True}

    # Auto-dispatch a SwarmTask
    try:
        from ..database import async_session_factory

        graph_type_map = {
            "crm:hot_lead": "crm",
            "crm:lead_created": "crm",
            "crm:support_ticket": "support",
            "crm:opportunity_created": "crm",
        }
        graph_type = graph_type_map.get(internal_event, "research")

        # Build task description from CRM event data
        contact_name = data.get("contact_name", data.get("name", "Unknown"))
        contact_email = data.get("contact_email", data.get("email", ""))
        description = f"CRM auto-dispatch: {event_type} for {contact_name} ({contact_email})"

        task_payload = {
            "trigger_event": internal_event,
            "crm_event": event_type,
            "crm_data": data,
            "playbook_id": matching_playbook["id"],
        }

        # Use Redis to enqueue directly (same pattern as swarms.py)
        from autoswarm_redis_pool import get_redis_pool
        import uuid

        task_id = str(uuid.uuid4())
        task_msg = json.dumps({
            "task_id": task_id,
            "graph_type": graph_type,
            "description": description,
            "assigned_agent_ids": [],
            "required_skills": ["crm-outreach"],
            "payload": task_payload,
            "playbook_id": matching_playbook["id"],
            "playbook": matching_playbook,
        })

        pool = get_redis_pool(url=settings.redis_url)
        await pool.execute_with_retry("xadd", "autoswarm:task-stream", {"data": task_msg})

        logger.info(
            "CRM auto-dispatch: task=%s event=%s playbook=%s",
            task_id,
            event_type,
            matching_playbook["name"],
        )

        # Track in PostHog
        try:
            from ..analytics import track
            track("system", "selva_crm_auto_dispatch", {
                "event": event_type,
                "playbook": matching_playbook["name"],
                "task_id": task_id,
                "contact_email": contact_email,
            })
        except Exception:
            pass

        return {
            "status": "dispatched",
            "task_id": task_id,
            "playbook": matching_playbook["name"],
            "graph_type": graph_type,
        }

    except Exception as exc:
        logger.exception("CRM auto-dispatch failed: %s", exc)
        return {"status": "error", "message": str(exc)}
