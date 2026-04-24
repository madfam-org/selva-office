"""Unified audit trail API — merges the four Selva RFC ledgers into one stream.

This endpoint is a *read-only* aggregator over:
- ``secret_audit_log``       (RFC 0005)
- ``github_admin_audit_log`` (RFC 0006)
- ``configmap_audit_log``    (RFC 0007)
- ``webhook_audit_log``      (RFC 0008)

It returns rows in a canonical ``UnifiedAuditEvent`` shape so cross-service
callers (notably ``switchyard-api``'s audit aggregator, which exposes the
consolidated view in ``app.enclii.dev/audit``) can merge these with rows
from other services without per-source de-serialization logic.

RBAC: self-or-admin. Non-admin callers are forced to ``actor = user.sub``.
Worker-token callers are treated as admin (they're internal service traffic).

Pagination: cursor-based. The cursor is the ISO-8601 timestamp of the last
row returned; pass it on the next request to continue strictly older. There
is intentionally no total count — the ledgers are append-only and unbounded,
and counting would defeat the index.

See also: ``nexus_api.routers.audit`` (generic per-request audit for the
``AuditLog`` middleware table) — that is a *different* surface.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    ConfigmapAuditLog,
    GithubAdminAuditLog,
    SecretAuditLog,
    WebhookAuditLog,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit-unified"])


# ---------------------------------------------------------------------------
# Canonical shape (must match ``switchyard-api/internal/audit.AuditEvent``)
# ---------------------------------------------------------------------------

SourceName = Literal[
    "selva_secret",
    "selva_github",
    "selva_config",
    "selva_webhook",
]


class UnifiedAuditEvent(BaseModel):
    """Canonical cross-service audit event shape.

    Fields are chosen to be the lowest common denominator across the four
    Selva ledgers. Source-specific fields (approval chain, hash prefixes,
    operation enum values) land in ``details`` so the UI can render them
    verbatim without the backend needing to know every ledger's schema.
    """

    timestamp: datetime
    actor: str | None = Field(
        None,
        description=(
            "Janua user sub or ``agent:<uuid>`` if the action was agent-driven. "
            "NULL only for legacy rows predating RFC 0005's actor_user_sub column."
        ),
    )
    actor_email: str | None = None
    source: SourceName
    category: Literal["secret", "github", "config", "webhook"]
    action: str
    target: str
    outcome: Literal["success", "failure", "denied"]
    request_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class UnifiedAuditListResponse(BaseModel):
    events: list[UnifiedAuditEvent]
    next_cursor: str | None = None


# ---------------------------------------------------------------------------
# Row → UnifiedAuditEvent mappers (one per Selva ledger)
# ---------------------------------------------------------------------------


def _outcome_from_status(status_str: str) -> Literal["success", "failure", "denied"]:
    """Map ledger ``status`` columns to the canonical outcome triad.

    The Selva ledgers use status values like ``applied`` / ``failed`` /
    ``denied`` / ``rolled_back``. Everything non-terminal/non-denied
    collapses to ``failure`` for UI display — forensic detail remains in
    ``details.status``.
    """
    s = (status_str or "").lower()
    if s in {"applied", "success", "succeeded", "completed"}:
        return "success"
    if s in {"denied", "rejected", "blocked"}:
        return "denied"
    return "failure"


def _secret_to_event(row: SecretAuditLog) -> UnifiedAuditEvent:
    actor = row.actor_user_sub or (f"agent:{row.agent_id}" if row.agent_id else None)
    target = (
        f"{row.target_cluster}/{row.target_namespace}/{row.target_secret_name}:{row.target_key}"
    )
    return UnifiedAuditEvent(
        timestamp=row.created_at,
        actor=actor,
        source="selva_secret",
        category="secret",
        action=row.operation,
        target=target,
        outcome=_outcome_from_status(row.status),
        request_id=None,  # RFC 0005 ties request_id to approval_request_id
        details={
            "status": row.status,
            "source": row.source,
            "rationale": row.rationale,
            "value_sha256_prefix": row.value_sha256_prefix,
            "predecessor_sha256_prefix": row.predecessor_sha256_prefix,
            "approval_request_id": str(row.approval_request_id),
            "approval_chain": row.approval_chain,
            "rollback_of_id": str(row.rollback_of_id) if row.rollback_of_id else None,
            "error_message": row.error_message,
        },
    )


def _github_to_event(row: GithubAdminAuditLog) -> UnifiedAuditEvent:
    actor = row.actor_user_sub or (f"agent:{row.agent_id}" if row.agent_id else None)
    parts = [row.target_org]
    if row.target_repo:
        parts.append(row.target_repo)
    if row.target_team_slug:
        parts.append(f"team:{row.target_team_slug}")
    if row.target_branch:
        parts.append(f"branch:{row.target_branch}")
    target = "/".join(parts)
    return UnifiedAuditEvent(
        timestamp=row.created_at,
        actor=actor,
        source="selva_github",
        category="github",
        action=row.operation,
        target=target,
        outcome=_outcome_from_status(row.status),
        request_id=row.request_id,
        details={
            "status": row.status,
            "rationale": row.rationale,
            "token_sha256_prefix": row.token_sha256_prefix,
            "request_body": row.request_body,
            "response_summary": row.response_summary,
            "approval_request_id": str(row.approval_request_id),
            "approval_chain": row.approval_chain,
            "rollback_of_id": str(row.rollback_of_id) if row.rollback_of_id else None,
            "error_message": row.error_message,
        },
    )


def _configmap_to_event(row: ConfigmapAuditLog) -> UnifiedAuditEvent:
    actor = row.actor_user_sub or (f"agent:{row.agent_id}" if row.agent_id else None)
    target = f"{row.target_cluster}/{row.target_namespace}/{row.target_configmap_name}"
    if row.target_key:
        target = f"{target}:{row.target_key}"
    return UnifiedAuditEvent(
        timestamp=row.created_at,
        actor=actor,
        source="selva_config",
        category="config",
        action=row.operation,
        target=target,
        outcome=_outcome_from_status(row.status),
        request_id=row.request_id,
        details={
            "status": row.status,
            "rationale": row.rationale,
            "hitl_level": row.hitl_level,
            "value_sha256_prefix": row.value_sha256_prefix,
            "previous_value_sha256_prefix": row.previous_value_sha256_prefix,
            "approval_request_id": str(row.approval_request_id),
            "approval_chain": row.approval_chain,
            "rollback_of_id": str(row.rollback_of_id) if row.rollback_of_id else None,
            "error_message": row.error_message,
        },
    )


def _webhook_to_event(row: WebhookAuditLog) -> UnifiedAuditEvent:
    actor = row.actor_user_sub or (f"agent:{row.agent_id}" if row.agent_id else None)
    target_parts = [row.provider]
    if row.webhook_id:
        target_parts.append(row.webhook_id)
    elif row.target_url_sha256_prefix:
        target_parts.append(f"url:{row.target_url_sha256_prefix}")
    target = "/".join(target_parts)
    return UnifiedAuditEvent(
        timestamp=row.created_at,
        actor=actor,
        source="selva_webhook",
        category="webhook",
        action=row.action,
        target=target,
        outcome=_outcome_from_status(row.status),
        request_id=row.request_id,
        details={
            "status": row.status,
            "rationale": row.rationale,
            "target_url_sha256_prefix": row.target_url_sha256_prefix,
            "events_registered": row.events_registered,
            "linked_secret_audit_id": (
                str(row.linked_secret_audit_id) if row.linked_secret_audit_id else None
            ),
            "resulting_secret_name": row.resulting_secret_name,
            "approval_request_id": str(row.approval_request_id),
            "approval_chain": row.approval_chain,
            "error_message": row.error_message,
        },
    )


# ---------------------------------------------------------------------------
# Aggregator query logic
# ---------------------------------------------------------------------------

# Per-source query config: (SQLAlchemy model, mapper fn, sort column, actor col).
# ``actor_col`` is the ``actor_user_sub`` column on each ledger; it's what we
# filter on when RBAC forces a non-admin caller to see only their own rows.
_SOURCES: dict[str, tuple[Any, Any, Any, Any]] = {
    "selva_secret": (
        SecretAuditLog,
        _secret_to_event,
        SecretAuditLog.created_at,
        SecretAuditLog.actor_user_sub,
    ),
    "selva_github": (
        GithubAdminAuditLog,
        _github_to_event,
        GithubAdminAuditLog.created_at,
        GithubAdminAuditLog.actor_user_sub,
    ),
    "selva_config": (
        ConfigmapAuditLog,
        _configmap_to_event,
        ConfigmapAuditLog.created_at,
        ConfigmapAuditLog.actor_user_sub,
    ),
    "selva_webhook": (
        WebhookAuditLog,
        _webhook_to_event,
        WebhookAuditLog.created_at,
        WebhookAuditLog.actor_user_sub,
    ),
}


def _parse_cursor(cursor: str | None) -> datetime | None:
    if not cursor:
        return None
    try:
        parsed = datetime.fromisoformat(cursor)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cursor format (expected ISO-8601): {cursor}",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _is_admin_or_service(user: dict[str, Any]) -> bool:
    roles = user.get("roles") or []
    return "admin" in roles or "service" in roles


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get("", response_model=UnifiedAuditListResponse)
@router.get("/", response_model=UnifiedAuditListResponse)
async def list_unified_audit(
    user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    since: datetime | None = Query(None, description="ISO-8601 lower bound (inclusive)"),
    until: datetime | None = Query(None, description="ISO-8601 upper bound (inclusive)"),
    source: list[str] | None = Query(
        None,
        description=(
            "Filter to a subset of the four Selva ledgers. Omit for all four. "
            "Values: selva_secret, selva_github, selva_config, selva_webhook."
        ),
    ),
    actor: str | None = Query(
        None,
        description=(
            "Filter by ``actor_user_sub``. Non-admin callers are server-side "
            "forced to their own ``sub`` regardless of this parameter."
        ),
    ),
    limit: int = Query(100, ge=1, le=500),
    cursor: str | None = Query(
        None, description="ISO-8601 timestamp from a prior response's next_cursor"
    ),
) -> UnifiedAuditListResponse:
    """Return a merged, timestamp-DESC-ordered stream across the 4 Selva ledgers.

    Query strategy: we fetch ``limit + 1`` rows from each requested source,
    merge in Python, sort, then slice to ``limit``. For ``limit=500`` and four
    sources that's up to 2004 rows materialized per request, which is bounded
    and cheap given the ``ix_*_audit_created`` indexes. If we ever need
    > 500-row pages we'll switch to an async heap-merge iterator.

    The ``next_cursor`` is the oldest timestamp we returned; the client passes
    it back as ``cursor`` on the next call to page strictly older.
    """
    # -- RBAC enforcement: non-admin → own rows only ---------------------
    if not _is_admin_or_service(user):
        caller_sub = user.get("sub")
        if not caller_sub:
            # Authenticated but no sub = malformed JWT; reject defensively.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token missing 'sub' claim",
            )
        actor = caller_sub  # Force, ignoring any user-supplied value.

    # -- Source filter validation ---------------------------------------
    if source:
        invalid = [s for s in source if s not in _SOURCES]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown source(s): {invalid}. Valid: {list(_SOURCES)}",
            )
        sources = source
    else:
        sources = list(_SOURCES.keys())

    cursor_ts = _parse_cursor(cursor)

    # -- Per-source fetch (parallelizable in a future pass) --------------
    # We fetch ``limit + 1`` to know whether a next page exists *per source*.
    # After merging we only need a single next_cursor across all sources.
    merged: list[UnifiedAuditEvent] = []
    for src_name in sources:
        model, mapper, sort_col, actor_col = _SOURCES[src_name]
        stmt = select(model)
        if since:
            stmt = stmt.where(sort_col >= since)
        if until:
            stmt = stmt.where(sort_col <= until)
        if cursor_ts:
            stmt = stmt.where(sort_col < cursor_ts)
        if actor:
            stmt = stmt.where(actor_col == actor)
        stmt = stmt.order_by(desc(sort_col)).limit(limit + 1)
        result = await db.execute(stmt)
        rows = result.scalars().all()
        merged.extend(mapper(row) for row in rows)

    # -- Merge, sort DESC by timestamp, slice to page --------------------
    merged.sort(key=lambda e: e.timestamp, reverse=True)
    page = merged[:limit]
    next_cursor: str | None = None
    if len(merged) > limit and page:
        # There are older rows beyond this page. Use the oldest event's
        # timestamp as the cursor (strictly-less-than on next request).
        next_cursor = page[-1].timestamp.isoformat()

    return UnifiedAuditListResponse(events=page, next_cursor=next_cursor)
