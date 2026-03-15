"""Add responded_by column to approval_requests.

Revision ID: 0012
Revises: 0011
Create Date: 2026-03-15
"""

from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "approval_requests",
        sa.Column("responded_by", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("approval_requests", "responded_by")
