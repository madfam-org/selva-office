"""Add skill marketplace tables for community skill publishing and ratings.

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_marketplace_entries",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("author", sa.String(255), nullable=False),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0.0"),
        sa.Column("yaml_content", sa.Text(), nullable=False),
        sa.Column("readme", sa.Text(), nullable=True),
        sa.Column("download_url", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("tags", sa.dialects.postgresql.JSON(), nullable=False, server_default="[]"),
        sa.Column("downloads", sa.Integer(), nullable=False, server_default="0"),
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_skill_marketplace_entries_org_id", "skill_marketplace_entries", ["org_id"]
    )

    op.create_table(
        "skill_ratings",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entry_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("skill_marketplace_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("entry_id", "user_id", name="uq_skill_rating_entry_user"),
    )
    op.create_index("ix_skill_ratings_org_id", "skill_ratings", ["org_id"])
    op.create_index("ix_skill_ratings_entry_id", "skill_ratings", ["entry_id"])


def downgrade() -> None:
    op.drop_index("ix_skill_ratings_entry_id", "skill_ratings")
    op.drop_index("ix_skill_ratings_org_id", "skill_ratings")
    op.drop_table("skill_ratings")
    op.drop_index("ix_skill_marketplace_entries_org_id", "skill_marketplace_entries")
    op.drop_table("skill_marketplace_entries")
