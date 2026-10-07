"""Add task_type + latency_ms to compute_token_ledger.

The inference proxy's ledger row now carries the request's X-Task-Type
routing label and the provider call's wall-clock latency, so usage can be
attributed per tenant AND per task (a pseudonymized-task exception is scoped
to one task type) without logging anything else. Metadata only: neither
column can hold a prompt or a completion. Both nullable so historical rows
and non-proxy debits stay valid.

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

_TABLE = "compute_token_ledger"


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column(_TABLE, "task_type"):
        op.add_column(_TABLE, sa.Column("task_type", sa.String(100), nullable=True))
    if not _has_column(_TABLE, "latency_ms"):
        op.add_column(_TABLE, sa.Column("latency_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    if _has_column(_TABLE, "latency_ms"):
        op.drop_column(_TABLE, "latency_ms")
    if _has_column(_TABLE, "task_type"):
        op.drop_column(_TABLE, "task_type")
