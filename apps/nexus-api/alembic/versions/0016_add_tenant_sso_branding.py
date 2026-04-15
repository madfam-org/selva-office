"""Add SSO and white-label branding columns to tenant_configs.

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enterprise SSO
    op.add_column(
        "tenant_configs",
        sa.Column("janua_connection_id", sa.String(255), nullable=True),
    )
    # White-label branding
    op.add_column(
        "tenant_configs",
        sa.Column("brand_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "tenant_configs",
        sa.Column("brand_logo_url", sa.String(500), nullable=True),
    )
    op.add_column(
        "tenant_configs",
        sa.Column("brand_primary_color", sa.String(7), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tenant_configs", "brand_primary_color")
    op.drop_column("tenant_configs", "brand_logo_url")
    op.drop_column("tenant_configs", "brand_name")
    op.drop_column("tenant_configs", "janua_connection_id")
