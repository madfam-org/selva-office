"""Add task_events table for full-stack observability.

Revision ID: 0011
Revises: 0010
Create Date: 2026-03-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swarm_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "agent_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("event_category", sa.String(50), nullable=False),
        sa.Column("node_id", sa.String(100), nullable=True),
        sa.Column("graph_type", sa.String(50), nullable=True),
        sa.Column("payload", sa.dialects.postgresql.JSON(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(50), nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("request_id", sa.String(100), nullable=True),
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
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])
    op.create_index("ix_task_events_agent_id", "task_events", ["agent_id"])
    op.create_index("ix_task_events_event_type", "task_events", ["event_type"])
    op.create_index("ix_task_events_event_category", "task_events", ["event_category"])
    op.create_index("ix_task_events_request_id", "task_events", ["request_id"])
    op.create_index("ix_task_events_org_id", "task_events", ["org_id"])
    op.create_index(
        "ix_task_events_task_created",
        "task_events",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_task_events_task_created", "task_events")
    op.drop_index("ix_task_events_org_id", "task_events")
    op.drop_index("ix_task_events_request_id", "task_events")
    op.drop_index("ix_task_events_event_category", "task_events")
    op.drop_index("ix_task_events_event_type", "task_events")
    op.drop_index("ix_task_events_agent_id", "task_events")
    op.drop_index("ix_task_events_task_id", "task_events")
    op.drop_table("task_events")
