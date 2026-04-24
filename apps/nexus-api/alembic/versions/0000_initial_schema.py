"""Create initial database schema.

Revision ID: 0000
Revises:
Create Date: 2026-03-06
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0000"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("max_agents", sa.Integer(), server_default="5"),
        sa.Column("position_x", sa.Integer(), server_default="0"),
        sa.Column("position_y", sa.Integer(), server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="coder"),
        sa.Column("status", sa.String(50), nullable=False, server_default="idle"),
        sa.Column("level", sa.Integer(), server_default="1"),
        sa.Column(
            "department_id",
            UUID(as_uuid=True),
            sa.ForeignKey("departments.id"),
            nullable=True,
        ),
        sa.Column("current_task_id", UUID(as_uuid=True), nullable=True),
        sa.Column("synergy_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        "approval_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=False,
        ),
        sa.Column("action_category", sa.String(100), nullable=False),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=False, server_default=""),
        sa.Column("urgency", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "swarm_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("graph_type", sa.String(50), nullable=False, server_default="sequential"),
        sa.Column("assigned_agent_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "compute_token_ledger",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column(
            "agent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agents.id"),
            nullable=True,
        ),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("swarm_tasks.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("compute_token_ledger")
    op.drop_table("swarm_tasks")
    op.drop_table("approval_requests")
    op.drop_table("agents")
    op.drop_table("departments")
