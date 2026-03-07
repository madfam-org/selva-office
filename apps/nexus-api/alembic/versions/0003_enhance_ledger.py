"""Add provider and model columns to compute_token_ledger.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-07
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "compute_token_ledger",
        sa.Column("provider", sa.String(50), nullable=True),
    )
    op.add_column(
        "compute_token_ledger",
        sa.Column("model", sa.String(100), nullable=True),
    )
    op.create_index(
        "ix_compute_token_ledger_org_created",
        "compute_token_ledger",
        ["org_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_compute_token_ledger_org_created", "compute_token_ledger")
    op.drop_column("compute_token_ledger", "model")
    op.drop_column("compute_token_ledger", "provider")
