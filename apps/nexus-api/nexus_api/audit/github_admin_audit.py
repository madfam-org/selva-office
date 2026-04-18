"""Append-only audit helpers for the ``github_admin_audit_log`` table.

RFC 0006 Sprint 1. Mirrors the signing pattern in ``secret_audit.py``:
the row's identifying fields are hashed at write time and the digest is
stored on the row. ``verify_signature`` recomputes the hash at audit
time so post-insert mutation is detectable.

The GitHub PAT itself is NEVER accepted here. Callers pass the 8-hex
prefix of ``SHA-256(pat)``, exactly matching the DB column width.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import GithubAdminAuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signature helpers — same shape as secret_audit.py::compute_signature
# ---------------------------------------------------------------------------


def _canonical_json(obj: Any) -> str:
    """Deterministic JSON encoding: sorted keys, compact separators.

    Used so the signature is stable across dict-insertion orderings.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def compute_signature(
    *,
    operation: str,
    target_org: str,
    target_repo: str | None,
    target_team_slug: str | None,
    target_branch: str | None,
    token_sha256_prefix: str,
    request_body: dict[str, Any],
    response_summary: dict[str, Any],
    rationale: str,
    approval_request_id: str,
    status: str,
    created_at: datetime,
) -> str:
    """SHA-256 tamper-evidence digest for a ``GithubAdminAuditLog`` row.

    NOT the PAT value -- that never reaches this module. This is a hash
    over the row's identifying fields so any post-insert mutation is
    detectable at audit time by replaying this function.
    """
    payload = "|".join(
        [
            operation,
            target_org,
            target_repo or "",
            target_team_slug or "",
            target_branch or "",
            token_sha256_prefix,
            _canonical_json(request_body),
            _canonical_json(response_summary),
            rationale,
            approval_request_id,
            status,
            created_at.isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_signature(entry: GithubAdminAuditLog) -> bool:
    """Recompute the digest on ``entry`` and compare to the stored value.

    Returns ``True`` iff the stored signature matches a fresh hash over
    the row's current fields. ``False`` means the row was mutated after
    insert (which is blocked at the DB level -- any False result is
    therefore a paging event).
    """
    created_at = entry.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    created_at = created_at.replace(microsecond=0)
    expected = compute_signature(
        operation=entry.operation,
        target_org=entry.target_org,
        target_repo=entry.target_repo,
        target_team_slug=entry.target_team_slug,
        target_branch=entry.target_branch,
        token_sha256_prefix=entry.token_sha256_prefix,
        request_body=entry.request_body or {},
        response_summary=entry.response_summary or {},
        rationale=entry.rationale,
        approval_request_id=str(entry.approval_request_id),
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

    Identical pattern to ``secret_audit._sync_session_factory``.
    """
    settings = get_settings()
    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    try:  # pragma: no cover — dependency-dependent branch
        import psycopg  # noqa: F401

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
    operation: str,
    target_org: str,
    target_repo: str | None,
    target_team_slug: str | None,
    target_branch: str | None,
    token_sha256_prefix: str,
    request_body: dict[str, Any],
    response_summary: dict[str, Any],
    rationale: str,
    status: str,
    error_message: str | None,
    request_id: str | None = None,
    approval_chain: list[dict[str, Any]] | None = None,
    rollback_of_id: str | None = None,
) -> None:
    """Append a row to ``github_admin_audit_log``. Never raises.

    ``token_sha256_prefix`` MUST be exactly 8 hex chars -- enforced at the
    DB level by a CHECK constraint. This function still short-circuits
    on bad input so a programming error surfaces as a log line instead
    of a migration-layer error.
    """
    if len(token_sha256_prefix) != 8:
        logger.error(
            "invalid token_sha256_prefix length=%d; refusing to record",
            len(token_sha256_prefix),
        )
        return

    created_at = datetime.now(UTC).replace(microsecond=0)
    signature = compute_signature(
        operation=operation,
        target_org=target_org,
        target_repo=target_repo,
        target_team_slug=target_team_slug,
        target_branch=target_branch,
        token_sha256_prefix=token_sha256_prefix,
        request_body=request_body,
        response_summary=response_summary,
        rationale=rationale,
        approval_request_id=approval_request_id,
        status=status,
        created_at=created_at,
    )

    try:
        import uuid as _uuid

        row = GithubAdminAuditLog(
            approval_request_id=_uuid.UUID(approval_request_id),
            agent_id=_uuid.UUID(agent_id) if agent_id else None,
            actor_user_sub=actor_user_sub,
            operation=operation,
            target_org=target_org,
            target_repo=target_repo,
            target_team_slug=target_team_slug,
            target_branch=target_branch,
            token_sha256_prefix=token_sha256_prefix,
            request_body=request_body,
            response_summary=response_summary,
            rationale=rationale,
            request_id=request_id,
            approval_chain=approval_chain or [],
            status=status,
            error_message=error_message,
            rollback_of_id=_uuid.UUID(rollback_of_id) if rollback_of_id else None,
            signature_sha256=signature,
            created_at=created_at,
        )
        with _new_session() as session:
            session.add(row)
            session.commit()
    except Exception:  # noqa: BLE001 — audit MUST NOT block the caller
        logger.error("github_admin_audit_log append failed", exc_info=True)


# ---------------------------------------------------------------------------
# Read path (drift detection + idempotency)
# ---------------------------------------------------------------------------


def last_team_membership_row(
    *,
    org: str,
    team_slug: str,
) -> GithubAdminAuditLog | None:
    """Return the most recent applied ``set_team_membership`` row for this team.

    Used by the ``audit_team_membership`` tool to diff the last known
    intended state against what GitHub currently reports.
    """
    try:
        with _new_session() as session:
            stmt = (
                select(GithubAdminAuditLog)
                .where(
                    and_(
                        GithubAdminAuditLog.target_org == org,
                        GithubAdminAuditLog.target_team_slug == team_slug,
                        GithubAdminAuditLog.operation == "set_team_membership",
                        GithubAdminAuditLog.status == "applied",
                    )
                )
                .order_by(GithubAdminAuditLog.created_at.desc())
                .limit(1)
            )
            return session.execute(stmt).scalars().first()
    except Exception:  # noqa: BLE001 — drift query failure is non-blocking
        logger.warning("last_team_membership_row query failed", exc_info=True)
        return None
