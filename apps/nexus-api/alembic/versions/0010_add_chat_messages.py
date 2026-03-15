"""Add chat_messages table for persistent chat history.

Revision ID: 0010
Revises: 0009
Create Date: 2026-03-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("room_id", sa.String(100), nullable=False),
        sa.Column("sender_session_id", sa.String(100), nullable=False, server_default=""),
        sa.Column("sender_name", sa.String(255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "org_id",
            sa.String(255),
            nullable=False,
            server_default="default",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_chat_messages_room_created", "chat_messages", ["room_id", "created_at"])
    op.create_index("ix_chat_messages_org_id", "chat_messages", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_org_id", "chat_messages")
    op.drop_index("ix_chat_messages_room_created", "chat_messages")
    op.drop_table("chat_messages")
