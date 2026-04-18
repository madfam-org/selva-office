"""Append-only audit helpers for the ``configmap_audit_log`` table.

RFC 0007 Sprint 1. Mirrors the ``secret_audit_log`` signing pattern in
``nexus_api.audit.secret_audit`` -- the ledger row's identifying fields
are hashed at write time and the digest is stored on the row.
``verify_signature`` recomputes the hash at audit time so post-insert
mutation is detectable.

Unlike secrets, ConfigMap operations ARE permitted to read values
(workers have ``get`` in their ConfigMap Role) -- but plaintext values
STILL never cross into this module. Callers hash the stringified value
offline and hand us only the 8-char prefix. Rationale from the RFC:
ConfigMaps legitimately carry semi-sensitive data (internal hostnames,
webhook URLs) that we don't want to leak via audit-table exfil.

The module also records the ``previous_value_sha256_prefix`` so a
forensic reviewer can reconstruct a key-flip diff without plaintext
on either side.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import get_settings
from ..models import ConfigmapAuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Signature helpers (mirrors secret_audit.compute_signature)
# ---------------------------------------------------------------------------


def compute_signature(
    *,
    target_cluster: str,
    target_namespace: str,
    target_configmap_name: str,
    target_key: str | None,
    operation: str,
    value_sha256_prefix: str | None,
    previous_value_sha256_prefix: str | None,
    rationale: str,
    hitl_level: str,
    approval_request_id: str,
    status: str,
    created_at: datetime,
) -> str:
    """SHA-256 tamper-evidence digest for a ``ConfigmapAuditLog`` row.

    This is NOT the ConfigMap value -- that never reaches this module.
    It's a hash over the row's identifying fields so any post-insert
    mutation is detectable at audit time by replaying this function.

    Nullable fields are serialized as empty strings so ``None`` and
    ``""`` produce the same digest. That's intentional: the goal is
    tamper-evidence on a known schema, not cryptographic uniqueness.
    """
    payload = "|".join(
        [
            target_cluster,
            target_namespace,
            target_configmap_name,
            target_key or "",
            operation,
            value_sha256_prefix or "",
            previous_value_sha256_prefix or "",
            rationale,
            hitl_level,
            approval_request_id,
            status,
            created_at.isoformat(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def verify_signature(entry: ConfigmapAuditLog) -> bool:
    """Recompute the digest on ``entry`` and compare to the stored value.

    Returns ``True`` iff the stored signature matches a fresh hash over
    the row's current fields. ``False`` means the row was mutated after
    insert (which is blocked at the DB level -- any ``False`` result is
    therefore a paging event).
    """
    created_at = entry.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    created_at = created_at.replace(microsecond=0)
    expected = compute_signature(
        target_cluster=entry.target_cluster,
        target_namespace=entry.target_namespace,
        target_configmap_name=entry.target_configmap_name,
        target_key=entry.target_key,
        operation=entry.operation,
        value_sha256_prefix=entry.value_sha256_prefix,
        previous_value_sha256_prefix=entry.previous_value_sha256_prefix,
        rationale=entry.rationale,
        hitl_level=entry.hitl_level,
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

    Same pattern as ``secret_audit._sync_session_factory``: audit writes
    are small and infrequent, a sync writer avoids pinning an event loop
    on the calling tool.
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
    request_id: str | None,
    target_cluster: str,
    target_namespace: str,
    target_configmap_name: str,
    target_key: str | None,
    operation: str,
    value_sha256_prefix: str | None,
    previous_value_sha256_prefix: str | None,
    rationale: str,
    hitl_level: str,
    status: str,
    error_message: str | None,
    approval_chain: list[dict[str, Any]] | None = None,
    rollback_of_id: str | None = None,
) -> None:
    """Append a row to ``configmap_audit_log``. Never raises.

    ``value_sha256_prefix`` and ``previous_value_sha256_prefix`` MUST
    each be exactly 8 hex chars when provided (callers compute them from
    ``sha256(value)[:8]``). Either can be ``None`` for operations that
    don't involve a value (list, delete-after-missing) or don't have a
    predecessor (create).

    This function does NOT receive or see the raw ConfigMap value.
    """
    for label, prefix in (
        ("value_sha256_prefix", value_sha256_prefix),
        ("previous_value_sha256_prefix", previous_value_sha256_prefix),
    ):
        if prefix is not None and len(prefix) != 8:
            logger.error(
                "invalid %s length=%d; refusing to record", label, len(prefix)
            )
            return

    created_at = datetime.now(UTC).replace(microsecond=0)
    signature = compute_signature(
        target_cluster=target_cluster,
        target_namespace=target_namespace,
        target_configmap_name=target_configmap_name,
        target_key=target_key,
        operation=operation,
        value_sha256_prefix=value_sha256_prefix,
        previous_value_sha256_prefix=previous_value_sha256_prefix,
        rationale=rationale,
        hitl_level=hitl_level,
        approval_request_id=approval_request_id,
        status=status,
        created_at=created_at,
    )

    try:
        import uuid as _uuid

        row = ConfigmapAuditLog(
            approval_request_id=_uuid.UUID(approval_request_id),
            agent_id=_uuid.UUID(agent_id) if agent_id else None,
            actor_user_sub=actor_user_sub,
            request_id=request_id,
            target_cluster=target_cluster,
            target_namespace=target_namespace,
            target_configmap_name=target_configmap_name,
            target_key=target_key,
            operation=operation,
            value_sha256_prefix=value_sha256_prefix,
            previous_value_sha256_prefix=previous_value_sha256_prefix,
            rationale=rationale,
            hitl_level=hitl_level,
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
        logger.error("configmap_audit_log append failed", exc_info=True)
