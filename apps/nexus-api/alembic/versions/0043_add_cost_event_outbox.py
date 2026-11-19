"""Add cost_event_outbox — Selva's durable outbox to Dhanam's cost ledger.

One row per ``cost.event.v1`` event built from ``compute_token_ledger``
(RFC 0050, ruling C13): the payload, its SHA-256, the delivery state
(``pending`` / ``sent`` / ``rejected``), attempts, backoff and a short error
code. Written only by ``python -m nexus_api.cost_events``, which stays off
until ``SELVA_COST_EVENTS_EMIT_ENABLED=true``; an empty table changes nothing.

Not a tenant table: no ``org_id`` column and no RLS policy (the org travels
inside the payload as an opaque reference). Additive and guarded like every
Selva migration, so a re-run is a no-op.

Revision ID: 0043
Revises: 0042
Create Date: 2026-11-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

_TABLE = "cost_event_outbox"


def _has_table(table: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if _has_table(_TABLE):
        return
    op.create_table(
        _TABLE,
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", sa.String(128), nullable=False),
        sa.Column("period_date", sa.Date(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("event_id", name="uq_cost_event_outbox_event_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'rejected')", name="ck_cost_event_outbox_status"
        ),
    )
    op.create_index("ix_cost_event_outbox_period_date", _TABLE, ["period_date"])
    op.create_index("ix_cost_event_outbox_status", _TABLE, ["status"])


def downgrade() -> None:
    if not _has_table(_TABLE):
        return
    op.drop_index("ix_cost_event_outbox_status", table_name=_TABLE)
    op.drop_index("ix_cost_event_outbox_period_date", table_name=_TABLE)
    op.drop_table(_TABLE)
