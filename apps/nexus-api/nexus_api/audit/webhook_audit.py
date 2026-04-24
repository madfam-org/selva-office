"""Append-only audit helpers for the ``webhook_audit_log`` table.

RFC 0008 Sprint 1. Mirrors ``secret_audit.py`` (RFC 0005 Sprint 1a):
rows are signed at write time with a SHA-256 over the identifying
fields so any post-insert mutation is detectable at audit time by
replaying ``compute_signature``.

This module NEVER sees the webhook signing secret (that flows via
``secret_audit.append_audit_row`` from the RFC 0005 path) and NEVER
sees the raw endpoint URL (only the 8-hex-char SHA-256 prefix). Webhook
URLs frequently embed authentication tokens in their paths, so even
the full URL is treated as sensitive.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import WebhookAuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signature helpers (mirrors secret_audit.compute_signature)
# ---------------------------------------------------------------------------


def compute_signature(
    *,
    provider: str,
    action: str,
    webhook_id: str | None,
    target_url_sha256_prefix: str | None,
    events_registered: list[str] | None,
    linked_secret_audit_id: str | None,
    resulting_secret_name: str | None,
    approval_request_id: str,
    rationale: str,
    status: str,
    created_at: datetime,
) -> str:
    """SHA-256 tamper-evidence digest for a ``WebhookAuditLog`` row.

    Combines the row's identifying fields into a deterministic payload
    and hashes. NEVER touches the webhook signing secret or the raw
    endpoint URL.
    """
    payload = "|".join(
        [
            provider,
            action,
            webhook_id or "",
            target_url_sha256_prefix or "",
            ",".join(sorted(events_registered)) if events_registered else "",
            linked_secret_audit_id or "",
            resulting_secret_name or "",
            approval_request_id,
            rationale,
            status,
            created_at.isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_signature(entry: WebhookAuditLog) -> bool:
    """Recompute the digest on ``entry`` and compare to the stored value.

    Returns ``True`` iff the stored signature matches a fresh hash over
    the row's current fields. ``False`` means the row was mutated after
    insert (which is blocked at the DB level — any False result is
    therefore a paging event).
    """
    created_at = entry.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    created_at = created_at.replace(microsecond=0)
    expected = compute_signature(
        provider=entry.provider,
        action=entry.action,
        webhook_id=entry.webhook_id,
        target_url_sha256_prefix=entry.target_url_sha256_prefix,
        events_registered=entry.events_registered,
        linked_secret_audit_id=(
            str(entry.linked_secret_audit_id) if entry.linked_secret_audit_id else None
        ),
        resulting_secret_name=entry.resulting_secret_name,
        approval_request_id=str(entry.approval_request_id),
        rationale=entry.rationale,
        status=entry.status,
        created_at=created_at,
    )
    return expected == entry.signature_sha256


# ---------------------------------------------------------------------------
# Write path (fire-and-forget, never blocks the tool on DB failure)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _sync_session_factory() -> sessionmaker[Session]:
    """Build a sync sessionmaker from the async DATABASE_URL.

    Same rationale as ``secret_audit._sync_session_factory``: audit
    writes are small and infrequent, and a sync writer avoids pinning
    an event loop on the calling tool.
    """
    settings = get_settings()
    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    try:  # pragma: no cover — dependency-dependent branch
        import psycopg  # noqa: F401  (validates driver availability)

        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    except Exception:  # noqa: BLE001 — fall through to psycopg2
        pass
    engine = create_engine(url, pool_pre_ping=True, pool_size=2, max_overflow=0)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _new_session() -> Session:
    """Return a sync Session for the audit writer."""
    return _sync_session_factory()()


def append_audit_row(
    *,
    approval_request_id: str,
    agent_id: str | None,
    actor_user_sub: str | None,
    provider: str,
    action: str,
    webhook_id: str | None,
    target_url_sha256_prefix: str | None,
    events_registered: list[str] | None,
    linked_secret_audit_id: str | None,
    resulting_secret_name: str | None,
    rationale: str,
    status: str,
    error_message: str | None,
    request_id: str | None = None,
    approval_chain: list[dict[str, Any]] | None = None,
) -> str | None:
    """Append a row to ``webhook_audit_log``. Never raises.

    Returns the newly written row's UUID as a string (so callers that
    want to back-link from the linked ``secret_audit_log`` row have a
    value), or ``None`` on failure.

    ``target_url_sha256_prefix`` MUST be exactly 8 hex chars OR ``None``.
    """
    if target_url_sha256_prefix is not None and len(target_url_sha256_prefix) != 8:
        logger.error(
            "invalid target_url_sha256_prefix length=%d; refusing to record",
            len(target_url_sha256_prefix),
        )
        return None

    created_at = datetime.now(UTC).replace(microsecond=0)
    signature = compute_signature(
        provider=provider,
        action=action,
        webhook_id=webhook_id,
        target_url_sha256_prefix=target_url_sha256_prefix,
        events_registered=events_registered,
        linked_secret_audit_id=linked_secret_audit_id,
        resulting_secret_name=resulting_secret_name,
        approval_request_id=approval_request_id,
        rationale=rationale,
        status=status,
        created_at=created_at,
    )

    try:
        import uuid as _uuid

        row = WebhookAuditLog(
            approval_request_id=_uuid.UUID(approval_request_id),
            agent_id=_uuid.UUID(agent_id) if agent_id else None,
            actor_user_sub=actor_user_sub,
            provider=provider,
            action=action,
            webhook_id=webhook_id,
            target_url_sha256_prefix=target_url_sha256_prefix,
            events_registered=events_registered,
            linked_secret_audit_id=(
                _uuid.UUID(linked_secret_audit_id) if linked_secret_audit_id else None
            ),
            resulting_secret_name=resulting_secret_name,
            approval_chain=approval_chain or [],
            rationale=rationale,
            status=status,
            error_message=error_message,
            request_id=request_id,
            signature_sha256=signature,
            created_at=created_at,
        )
        with _new_session() as session:
            session.add(row)
            session.commit()
            return str(row.id)
    except Exception:  # noqa: BLE001 — audit MUST NOT block the caller
        logger.error("webhook_audit_log append failed", exc_info=True)
        return None


def find_by_webhook_id(
    *,
    provider: str,
    webhook_id: str,
) -> list[WebhookAuditLog]:
    """Return all rows for ``(provider, webhook_id)``, newest first.

    Useful for the "is this webhook still managed?" check during
    rotation/retirement flows (Sprint 2).
    """
    try:
        with _new_session() as session:
            stmt = (
                select(WebhookAuditLog)
                .where(
                    and_(
                        WebhookAuditLog.provider == provider,
                        WebhookAuditLog.webhook_id == webhook_id,
                    )
                )
                .order_by(WebhookAuditLog.created_at.desc())
            )
            return list(session.execute(stmt).scalars().all())
    except Exception:  # noqa: BLE001
        logger.warning("webhook_audit_log lookup failed", exc_info=True)
        return []
