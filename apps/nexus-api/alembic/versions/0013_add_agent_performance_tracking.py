"""Add agent performance tracking columns.

Revision ID: 0013
Revises: 0012
Create Date: 2026-03-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agents",
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agents",
        sa.Column("tasks_failed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agents",
        sa.Column("approval_success_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agents",
        sa.Column("approval_denial_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "agents",
        sa.Column("avg_task_duration_seconds", sa.Float(), nullable=True),
    )
    op.add_column(
        "agents",
        sa.Column("last_task_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agents", "last_task_at")
    op.drop_column("agents", "avg_task_duration_seconds")
    op.drop_column("agents", "approval_denial_count")
    op.drop_column("agents", "approval_success_count")
    op.drop_column("agents", "tasks_failed")
    op.drop_column("agents", "tasks_completed")
