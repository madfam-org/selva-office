"""Add calendar_connections table for Google/Microsoft calendar integration.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_connections",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=False),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column(
            "org_id",
            sa.String(255),
            nullable=False,
            server_default="default",
        ),
        sa.Column(
            "connected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_calendar_connections_org_id", "calendar_connections", ["org_id"])
    op.create_index("ix_calendar_connections_user_id", "calendar_connections", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_calendar_connections_user_id", "calendar_connections")
    op.drop_index("ix_calendar_connections_org_id", "calendar_connections")
    op.drop_table("calendar_connections")
