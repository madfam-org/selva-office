"""Add artifacts table for task output persistence.

Revision ID: 0006
Revises: 0005
Create Date: 2026-03-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "artifacts",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "task_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("swarm_tasks.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("agent_id", sa.String(255), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False, server_default="text/plain"),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.dialects.postgresql.JSON(), nullable=True),
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
    op.create_index("ix_artifacts_content_hash", "artifacts", ["content_hash"])
    op.create_index("ix_artifacts_org_id", "artifacts", ["org_id"])
    op.create_index("ix_artifacts_task_id", "artifacts", ["task_id"])


def downgrade() -> None:
    op.drop_index("ix_artifacts_task_id", "artifacts")
    op.drop_index("ix_artifacts_org_id", "artifacts")
    op.drop_index("ix_artifacts_content_hash", "artifacts")
    op.drop_table("artifacts")
