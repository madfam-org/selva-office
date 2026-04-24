"""Attribution glue — preserves `lead_id` across the conversion funnel.

T3.2 contract (see /internal-devops/docs/attribution-contract.md):

    lead.captured (phyne-crm)
        -> lead.qualified (autoswarm-office, this module)
            -> playbook.sent (autoswarm-office, this module)
                -> checkout.completed (dhanam)
                    -> subscription.created (dhanam)

The `lead_id` is an opaque string — typically a UUID4 minted by PhyneCRM
when a lead is first captured. This module:

1. Extracts a stable `lead_id` from inbound CRM events. When PhyneCRM
   does not provide one, a deterministic fallback is derived from
   (contact_email, activity_id) so retries collapse to the same id.
2. Emits PostHog events with `distinct_id = lead_id` so the funnel is
   anonymous up to conversion. Dhanam will call `posthog.alias()`
   when the lead converts to link the anonymous `lead_id` to the
   authenticated `user_sub`.

The `lead_id` MUST be threaded through every hop:
- CRM webhook -> SwarmTask.payload["lead_id"]
- SwarmTask.payload -> CRM graph state["lead_id"]
- graph state -> email tool metadata (utm_campaign + reply-to chain)
- email send -> PostHog `playbook.sent` event

Keep this module dependency-light: it is imported from webhook handlers
that must not pull heavy graph / worker code.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

from .analytics import track

logger = logging.getLogger(__name__)

# Event names for the attribution funnel. Centralised here so downstream
# repos (phyne-crm, dhanam) can import the same constants once this
# module is re-exported via a shared package.
EVENT_LEAD_CAPTURED = "lead.captured"  # emitted by phyne-crm
EVENT_LEAD_QUALIFIED = "lead.qualified"  # emitted here
EVENT_PLAYBOOK_SENT = "playbook.sent"  # emitted here
EVENT_CHECKOUT_COMPLETED = "checkout.completed"  # emitted by dhanam
EVENT_SUBSCRIPTION_CREATED = "subscription.created"  # emitted by dhanam


def extract_lead_id(crm_event_data: dict[str, Any]) -> str:
    """Return a stable `lead_id` for a CRM event.

    Preference order:
        1. `crm_event_data["lead_id"]` (preferred, PhyneCRM-minted UUID)
        2. `crm_event_data["id"]` (PhyneCRM contact id)
        3. Deterministic SHA-256 fallback over contact_email + activity_id
        4. Freshly minted UUID4 (last resort — breaks dedup guarantees)

    The returned id is always a non-empty string, URL-safe.
    """
    explicit = crm_event_data.get("lead_id")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    contact_id = crm_event_data.get("id") or crm_event_data.get("contact_id")
    if isinstance(contact_id, str) and contact_id.strip():
        return contact_id.strip()

    # Deterministic fallback: derive a stable id from contact identifiers
    # so webhook retries do not mint new lead ids.
    contact_email = str(crm_event_data.get("contact_email") or crm_event_data.get("email") or "")
    activity_id = str(crm_event_data.get("activity_id") or "")
    if contact_email or activity_id:
        seed = f"{contact_email}|{activity_id}".encode()
        digest = hashlib.sha256(seed).hexdigest()[:32]
        return f"lead_{digest}"

    # Last resort — non-deterministic. Log so we notice in staging.
    fallback = str(uuid.uuid4())
    logger.warning(
        "extract_lead_id: no stable identifiers in CRM event, minted fresh uuid=%s",
        fallback,
    )
    return fallback


def emit_lead_qualified(
    lead_id: str,
    *,
    trigger_event: str,
    playbook_name: str,
    task_id: str,
    utm_source: str = "selva",
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit `lead.qualified` when a CRM event matches a playbook.

    `distinct_id` is the anonymous `lead_id` — never the contact email
    (using the email would fork the funnel into a second distinct_id
    once the user authenticates with Janua / Dhanam).
    """
    if not lead_id:
        logger.debug("emit_lead_qualified: empty lead_id, skipping")
        return
    properties: dict[str, Any] = {
        "lead_id": lead_id,
        "trigger_event": trigger_event,
        "playbook": playbook_name,
        "task_id": task_id,
        "utm_source": utm_source,
    }
    if extra:
        properties.update(extra)
    track(lead_id, EVENT_LEAD_QUALIFIED, properties)


def emit_playbook_sent(
    lead_id: str,
    *,
    playbook_name: str,
    task_id: str,
    channel: str,
    recipient_domain: str | None = None,
    utm_campaign: str = "hot_lead_auto",
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit `playbook.sent` after a playbook successfully dispatches a
    user-facing action (email, SMS, etc.).

    `recipient_domain` intentionally excludes the local-part of the
    email to keep the event PII-safe while still enabling domain-level
    funnel segmentation.
    """
    if not lead_id:
        logger.debug("emit_playbook_sent: empty lead_id, skipping")
        return
    properties: dict[str, Any] = {
        "lead_id": lead_id,
        "playbook": playbook_name,
        "task_id": task_id,
        "channel": channel,
        "utm_campaign": utm_campaign,
    }
    if recipient_domain:
        properties["recipient_domain"] = recipient_domain
    if extra:
        properties.update(extra)
    track(lead_id, EVENT_PLAYBOOK_SENT, properties)


def domain_of(email: str) -> str | None:
    """Return the domain part of an email address, or None."""
    if not isinstance(email, str) or "@" not in email:
        return None
    _, _, domain = email.partition("@")
    return domain.lower().strip() or None
