"""PhyneCRM webhook handler — receives CRM events and auto-dispatches tasks.

Maps CRM lifecycle events to SwarmTask dispatch via the playbook system.
Only dispatches if a matching enabled playbook exists for the event.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request

from ..attribution import (
    domain_of,
    emit_lead_qualified,
    extract_lead_id,
)
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
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc

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
        logger.info(
            "No matching playbook for CRM event %s (%s), skipping dispatch",
            event_type,
            internal_event,
        )
        return {"status": "ok", "event": event_type, "no_playbook": True}

    # Auto-dispatch a SwarmTask
    try:
        graph_type_map = {
            "crm:hot_lead": "crm",
            "crm:lead_created": "crm",
            "crm:support_ticket": "support",
            "crm:opportunity_created": "crm",
        }
        graph_type = graph_type_map.get(internal_event, "research")

        # Build task description from CRM event data. PII-safe: reference
        # lead_id, not contact_name, so logs / ops dashboards stay clean.
        contact_email = data.get("contact_email", data.get("email", ""))

        # T3.2 — extract a stable `lead_id` and thread it through the funnel.
        lead_id = extract_lead_id(data)

        description = f"CRM auto-dispatch: {event_type} for lead:{lead_id}"

        task_payload = {
            "trigger_event": internal_event,
            "crm_event": event_type,
            "crm_data": data,
            "playbook_id": matching_playbook["id"],
            # Attribution glue — preserved across the hop to the worker.
            "lead_id": lead_id,
            "utm_source": data.get("utm_source", "selva"),
            "utm_campaign": data.get("utm_campaign", "hot_lead_auto"),
        }

        # Use Redis to enqueue directly (same pattern as swarms.py)
        import uuid

        from selva_redis_pool import get_redis_pool

        task_id = str(uuid.uuid4())
        task_msg = json.dumps(
            {
                "task_id": task_id,
                "graph_type": graph_type,
                "description": description,
                "assigned_agent_ids": [],
                "required_skills": ["crm-outreach"],
                "payload": task_payload,
                "playbook_id": matching_playbook["id"],
                "playbook": matching_playbook,
                # Promote lead_id to a top-level field for downstream consumers
                # (worker initial_state loader, ops dashboards) that don't
                # want to reach into payload.
                "lead_id": lead_id,
            }
        )

        pool = get_redis_pool(url=settings.redis_url)
        await pool.execute_with_retry("xadd", "autoswarm:task-stream", {"data": task_msg})

        logger.info(
            "CRM auto-dispatch: task=%s event=%s playbook=%s",
            task_id,
            event_type,
            matching_playbook["name"],
        )

        # T3.2 attribution funnel — emit `lead.qualified` with the
        # anonymous lead_id as distinct_id. Never use contact_email as
        # distinct_id: that would fork the funnel once the user
        # authenticates with Janua.
        try:
            emit_lead_qualified(
                lead_id,
                trigger_event=internal_event,
                playbook_name=matching_playbook["name"],
                task_id=task_id,
                utm_source=task_payload.get("utm_source", "selva"),
                extra={
                    "crm_event": event_type,
                    "graph_type": graph_type,
                    "recipient_domain": domain_of(contact_email),
                },
            )
        except Exception:
            logger.debug("emit_lead_qualified failed (non-fatal)", exc_info=True)

        # Legacy ops event kept for the existing dashboards — distinct
        # from the attribution funnel above.
        try:
            from ..analytics import track

            track(
                "system",
                "selva_crm_auto_dispatch",
                {
                    "event": event_type,
                    "playbook": matching_playbook["name"],
                    "task_id": task_id,
                    "lead_id": lead_id,
                },
            )
        except Exception:
            pass

        return {
            "status": "dispatched",
            "task_id": task_id,
            "playbook": matching_playbook["name"],
            "graph_type": graph_type,
            "lead_id": lead_id,
        }

    except Exception as exc:
        logger.exception("CRM auto-dispatch failed: %s", exc)
        return {"status": "error", "message": str(exc)}
