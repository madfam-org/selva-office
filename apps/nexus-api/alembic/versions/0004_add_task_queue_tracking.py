"""Add task queue tracking columns to swarm_tasks.

Revision ID: 0004
Revises: 0003
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "swarm_tasks",
        sa.Column("stream_message_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "swarm_tasks",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "swarm_tasks",
        sa.Column("worker_id", sa.String(255), nullable=True),
    )
    op.add_column(
        "swarm_tasks",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "swarm_tasks",
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_swarm_tasks_status_created_at",
        "swarm_tasks",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_swarm_tasks_status_created_at", "swarm_tasks")
    op.drop_column("swarm_tasks", "error_message")
    op.drop_column("swarm_tasks", "started_at")
    op.drop_column("swarm_tasks", "worker_id")
    op.drop_column("swarm_tasks", "retry_count")
    op.drop_column("swarm_tasks", "stream_message_id")
