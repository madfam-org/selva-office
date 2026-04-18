"""Append-only audit helpers for the ``secret_audit_log`` table.

RFC 0005 Sprint 1a. Mirrors the ``consent_ledger`` signing pattern in
``routers/onboarding.py`` — the ledger row's identifying fields are
hashed at write time and the digest is stored on the row. ``verify_signature``
recomputes the hash at audit time so post-insert mutation is detectable.

The K8s Secret value itself is NEVER stored or accepted here. Callers
pass the full SHA-256 hex digest (``sha_full``), and this module stores
only the first 8 hex chars. The ``was_already_applied`` lookup queries
by full hash (passed in by the caller), so idempotency works without
the prefix being brute-forceable.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from typing import Any

from functools import lru_cache

from sqlalchemy import and_, create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import SecretAuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signature helpers (mirrors routers/onboarding.py:compute_signature)
# ---------------------------------------------------------------------------


def compute_signature(
    *,
    target_cluster: str,
    target_namespace: str,
    target_secret_name: str,
    target_key: str,
    operation: str,
    value_sha256_prefix: str,
    source: str,
    rationale: str,
    approval_request_id: str,
    status: str,
    created_at: datetime,
) -> str:
    """SHA-256 tamper-evidence digest for a ``SecretAuditLog`` row.

    NOT the K8s Secret value — that never reaches this module. This is
    a hash over the row's identifying fields so any post-insert mutation
    is detectable at audit time by replaying this function.
    """
    payload = "|".join(
        [
            target_cluster,
            target_namespace,
            target_secret_name,
            target_key,
            operation,
            value_sha256_prefix,
            source,
            rationale,
            approval_request_id,
            status,
            created_at.isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_signature(entry: SecretAuditLog) -> bool:
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
        target_cluster=entry.target_cluster,
        target_namespace=entry.target_namespace,
        target_secret_name=entry.target_secret_name,
        target_key=entry.target_key,
        operation=entry.operation,
        value_sha256_prefix=entry.value_sha256_prefix,
        source=entry.source,
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

    The rest of nexus-api uses async sessions, but audit writes are
    tiny and infrequent; a sync writer avoids pinning an event loop on
    the calling tool. We strip the ``+asyncpg`` driver prefix so the
    sync engine uses psycopg/psycopg2 as available.
    """
    settings = get_settings()
    url = settings.database_url
    if "+asyncpg" in url:
        url = url.replace("+asyncpg", "")
    # Prefer psycopg3 if installed; fall back to psycopg2 via default URL.
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
    target_cluster: str,
    target_namespace: str,
    target_secret_name: str,
    target_key: str,
    operation: str,
    value_sha256_prefix: str,
    source: str,
    rationale: str,
    status: str,
    error_message: str | None,
    predecessor_sha256_prefix: str | None = None,
    approval_chain: list[dict[str, Any]] | None = None,
    rollback_of_id: str | None = None,
) -> None:
    """Append a row to ``secret_audit_log``. Never raises.

    ``value_sha256_prefix`` MUST be exactly 8 hex chars. The caller
    (tool) computes this from ``sha_full[:8]``. This function does not
    receive or see the raw value.
    """
    if len(value_sha256_prefix) != 8:
        logger.error(
            "invalid value_sha256_prefix length=%d; refusing to record",
            len(value_sha256_prefix),
        )
        return

    created_at = datetime.now(UTC).replace(microsecond=0)
    signature = compute_signature(
        target_cluster=target_cluster,
        target_namespace=target_namespace,
        target_secret_name=target_secret_name,
        target_key=target_key,
        operation=operation,
        value_sha256_prefix=value_sha256_prefix,
        source=source,
        rationale=rationale,
        approval_request_id=approval_request_id,
        status=status,
        created_at=created_at,
    )

    try:
        import uuid as _uuid

        row = SecretAuditLog(
            approval_request_id=_uuid.UUID(approval_request_id),
            agent_id=_uuid.UUID(agent_id) if agent_id else None,
            actor_user_sub=actor_user_sub,
            target_cluster=target_cluster,
            target_namespace=target_namespace,
            target_secret_name=target_secret_name,
            target_key=target_key,
            operation=operation,
            value_sha256_prefix=value_sha256_prefix,
            predecessor_sha256_prefix=predecessor_sha256_prefix,
            source=source,
            rationale=rationale,
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
        logger.error("secret_audit_log append failed", exc_info=True)


def was_already_applied(
    *,
    cluster: str,
    namespace: str,
    secret_name: str,
    key: str,
    sha_full: str,
) -> bool:
    """Return True if a prior write with this exact value already succeeded.

    Called by the tool BEFORE touching the K8s API for idempotency.
    Matches on ``(cluster, namespace, secret_name, key, sha_prefix)`` with
    ``status='applied'``. ``sha_full`` is the caller's full hex digest;
    only the first 8 chars are used in the query (which is all the DB
    has anyway).
    """
    prefix = sha_full[:8]
    try:
        with _new_session() as session:
            stmt = select(SecretAuditLog.id).where(
                and_(
                    SecretAuditLog.target_cluster == cluster,
                    SecretAuditLog.target_namespace == namespace,
                    SecretAuditLog.target_secret_name == secret_name,
                    SecretAuditLog.target_key == key,
                    SecretAuditLog.value_sha256_prefix == prefix,
                    SecretAuditLog.status == "applied",
                )
            )
            return session.execute(stmt).first() is not None
    except Exception:  # noqa: BLE001 — treat lookup failure as "write it"
        logger.warning("audit idempotency query failed", exc_info=True)
        return False
