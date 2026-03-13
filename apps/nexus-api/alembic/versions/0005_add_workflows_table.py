"""Add workflows table for custom workflow definitions.

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0.0"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("yaml_content", sa.Text(), nullable=False),
        sa.Column(
            "org_id",
            sa.String(255),
            nullable=False,
            server_default="default",
            index=True,
        ),
        sa.Column(
            "created_at",
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
    op.create_index("ix_workflows_org_name", "workflows", ["org_id", "name"])

    # Add workflow_id column to swarm_tasks for custom workflow dispatch
    op.add_column(
        "swarm_tasks",
        sa.Column("workflow_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_swarm_tasks_workflow_id",
        "swarm_tasks",
        "workflows",
        ["workflow_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_swarm_tasks_workflow_id", "swarm_tasks", type_="foreignkey")
    op.drop_column("swarm_tasks", "workflow_id")
    op.drop_index("ix_workflows_org_name", "workflows")
    op.drop_table("workflows")
