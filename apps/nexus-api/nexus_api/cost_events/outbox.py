"""Durable outbox for ``cost.event.v1`` events (table ``cost_event_outbox``).

One row per event id. The sweep rebuilds the closed days of its window and
``sync_outbox`` makes the table match:

* a new id → ``pending``;
* an id whose payload changed (late ledger rows, a grant or mapping edit) →
  the new payload, ``pending`` again (Dhanam answers ``updated`` for the same
  ``(source, id)``);
* an id of a rebuilt day that is no longer built → if Dhanam has it, the same
  payload with ``status: cancelled`` goes out (``pending``); if Dhanam never
  accepted it, the row is deleted.

``pending`` rows are sent in batches of at most 500; a transient failure backs
the batch off (``next_attempt_at``), a 400 marks the refused rows ``rejected``
with error CODES only. Not a tenant table: no ``org_id`` column, so no RLS
policy (the org travels inside the payload as an opaque ``client_ref``).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    delete,
    func,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base

PENDING = "pending"
SENT = "sent"
REJECTED = "rejected"

CREATED = "created"
UPDATED = "updated"
CANCELLED = "cancelled"
DELETED = "deleted"
UNCHANGED = "unchanged"

#: Backoff after a transient failure: 1, 2, 4 … minutes, capped at 6 hours.
MAX_BACKOFF = timedelta(hours=6)


def _now() -> datetime:
    return datetime.now(tz=UTC)


class CostEventOutbox(Base):
    """One ``cost.event.v1`` event and its delivery state."""

    __tablename__ = "cost_event_outbox"
    __table_args__ = (
        UniqueConstraint("event_id", name="uq_cost_event_outbox_event_id"),
        CheckConstraint(
            "status IN ('pending', 'sent', 'rejected')", name="ck_cost_event_outbox_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    period_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=PENDING, index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: A short code ("http_503", "amount_minor"), never a message or a payload.
    last_error: Mapped[str | None] = mapped_column(String(64))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


def payload_sha256(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _cancelled(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "status": "cancelled"}


def _repend(row: CostEventOutbox, payload: dict[str, Any], digest: str, now: datetime) -> None:
    row.payload = payload
    row.payload_sha256 = digest
    row.status = PENDING
    row.attempts = 0
    row.next_attempt_at = None
    row.last_error = None
    row.updated_at = now


async def sync_outbox(
    db: AsyncSession,
    events: dict[str, dict[str, Any]],
    event_days: dict[str, date],
    rebuilt_days: Iterable[date],
    *,
    replay: bool = False,
) -> Counter[str]:
    """Make the outbox rows of ``rebuilt_days`` match ``events``. Returns change counts.

    ``replay`` re-pends unchanged ``sent`` / ``rejected`` rows of those days too.
    """
    days = sorted(set(rebuilt_days))
    changes: Counter[str] = Counter()
    if not days:
        return changes
    now = _now()
    existing = {
        row.event_id: row
        for row in (
            await db.execute(select(CostEventOutbox).where(CostEventOutbox.period_date.in_(days)))
        ).scalars()
    }
    for eid, payload in events.items():
        digest = payload_sha256(payload)
        row = existing.pop(eid, None)
        if row is None:
            db.add(
                CostEventOutbox(
                    event_id=eid,
                    period_date=event_days[eid],
                    payload=payload,
                    payload_sha256=digest,
                    status=PENDING,
                    attempts=0,
                    created_at=now,
                    updated_at=now,
                )
            )
            changes[CREATED] += 1
        elif row.payload_sha256 != digest or (replay and row.status != PENDING):
            _repend(row, payload, digest, now)
            changes[UPDATED] += 1
        else:
            changes[UNCHANGED] += 1
    for row in existing.values():
        if row.payload.get("status") == "cancelled":
            if replay and row.status != PENDING:
                _repend(row, row.payload, row.payload_sha256, now)
                changes[CANCELLED] += 1
            else:
                changes[UNCHANGED] += 1
        elif row.sent_at is not None:
            # Dhanam holds it: tell it the group no longer exists.
            cancelled = _cancelled(row.payload)
            _repend(row, cancelled, payload_sha256(cancelled), now)
            changes[CANCELLED] += 1
        else:
            await db.execute(delete(CostEventOutbox).where(CostEventOutbox.id == row.id))
            changes[DELETED] += 1
    await db.flush()
    return changes


async def due_rows(db: AsyncSession, limit: int) -> list[CostEventOutbox]:
    """``pending`` rows whose backoff has passed, oldest day first."""
    now = _now()
    result = await db.execute(
        select(CostEventOutbox)
        .where(CostEventOutbox.status == PENDING)
        .where(
            or_(
                CostEventOutbox.next_attempt_at.is_(None),
                CostEventOutbox.next_attempt_at <= now,
            )
        )
        .order_by(CostEventOutbox.period_date, CostEventOutbox.event_id)
        .limit(limit)
    )
    return list(result.scalars())


async def pending_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count()).select_from(CostEventOutbox).where(CostEventOutbox.status == PENDING)
    )
    return int(result.scalar_one())


def backoff(attempts: int) -> timedelta:
    minutes = 2 ** max(0, min(attempts - 1, 12))
    return min(timedelta(minutes=minutes), MAX_BACKOFF)


def mark_sent(rows: Iterable[CostEventOutbox]) -> None:
    now = _now()
    for row in rows:
        row.status = SENT
        row.attempts += 1
        row.sent_at = now
        row.next_attempt_at = None
        row.last_error = None
        row.updated_at = now


def mark_rejected(row: CostEventOutbox, codes: list[str]) -> None:
    now = _now()
    row.status = REJECTED
    row.attempts += 1
    row.last_error = (",".join(sorted(set(codes))) or "unspecified")[:64]
    row.updated_at = now


def mark_retry(rows: Iterable[CostEventOutbox], code: str) -> None:
    """Leave the rows pending, backed off (transient) or as-is (an operator problem)."""
    now = _now()
    for row in rows:
        row.attempts += 1
        row.next_attempt_at = now + backoff(row.attempts)
        row.last_error = code[:64]
        row.updated_at = now
