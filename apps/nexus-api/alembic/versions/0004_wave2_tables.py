"""Alembic migration: add session_checkpoints and approval_requests tables.

Revision ID: 0004_wave2_tables
Revises: 0003_schedules (assumed previous)
Create Date: 2026-04-14
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_wave2_tables"
down_revision = "0003_schedules"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── approval_requests (Gap 2) ────────────────────────────────────────
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(255), nullable=False, index=True),
        sa.Column("command", sa.Text, nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "approved", "denied", "expired", name="approvalstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(255), nullable=True),
    )
    op.create_index("ix_approval_requests_run_id", "approval_requests", ["run_id"])

    # ── session_checkpoints (Next-Tier: Checkpoint/Rollback) ─────────────
    op.create_table(
        "session_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(255), nullable=False, index=True),
        sa.Column("phase", sa.String(64), nullable=False),
        sa.Column("phase_index", sa.Integer, nullable=False),
        sa.Column("state_json", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_session_checkpoints_run_id", "session_checkpoints", ["run_id"])


def downgrade() -> None:
    op.drop_table("session_checkpoints")
    op.drop_index("ix_approval_requests_run_id")
    op.drop_table("approval_requests")
    op.execute("DROP TYPE IF EXISTS approvalstatus")
