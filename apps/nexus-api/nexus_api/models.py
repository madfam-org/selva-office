"""SQLAlchemy ORM models for the Selva Nexus database."""

from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Department(Base):
    """A virtual office department that houses agents."""

    __tablename__ = "departments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    max_agents: Mapped[int] = mapped_column(Integer, default=5)
    position_x: Mapped[int] = mapped_column(Integer, default=0)
    position_y: Mapped[int] = mapped_column(Integer, default=0)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    agents: Mapped[list[Agent]] = relationship(
        "Agent", back_populates="department", lazy="selectin"
    )


class Agent(Base):
    """A swarm agent that belongs to a department and executes tasks."""

    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="coder")
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="idle")
    level: Mapped[int] = mapped_column(Integer, default=1)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("departments.id"), nullable=True
    )
    current_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    skill_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    synergy_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    # Performance tracking (migration 0013)
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approval_denial_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_task_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_task_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    department: Mapped[Department | None] = relationship(
        "Department", back_populates="agents", lazy="selectin"
    )


class ApprovalRequest(Base):
    """A human-in-the-loop approval request created when an agent hits an interrupt."""

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=False
    )
    action_category: Mapped[str] = mapped_column(String(100), nullable=False)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False, default="")
    urgency: Mapped[str] = mapped_column(String(20), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    agent: Mapped[Agent] = relationship("Agent", lazy="selectin")


class SwarmTask(Base):
    """A task dispatched to one or more agents in the swarm."""

    __tablename__ = "swarm_tasks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    graph_type: Mapped[str] = mapped_column(String(50), nullable=False, default="sequential")
    assigned_agent_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Queue tracking (migration 0004)
    stream_message_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Workflow reference (migration 0005)
    workflow_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )


class Workflow(Base):
    """A custom workflow definition stored as YAML."""

    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    description: Mapped[str] = mapped_column(Text, default="")
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Artifact(Base):
    """A task output artifact persisted in storage."""

    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("swarm_tasks.id", ondelete="SET NULL"), nullable=True
    )
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False, default="text/plain")
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ComputeTokenLedger(Base):
    """Immutable ledger of compute token debits and credits."""

    __tablename__ = "compute_token_ledger"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("swarm_tasks.id"), nullable=True
    )
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SkillMarketplaceEntry(Base):
    """A published skill available in the marketplace for installation."""

    __tablename__ = "skill_marketplace_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    readme: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tags: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    downloads: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    ratings: Mapped[list[SkillRating]] = relationship(
        "SkillRating",
        back_populates="entry",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class SkillRating(Base):
    """A user rating and optional review for a marketplace skill entry."""

    __tablename__ = "skill_ratings"
    __table_args__ = (
        UniqueConstraint("entry_id", "user_id", name="uq_skill_rating_entry_user"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_marketplace_entries.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    review: Mapped[str | None] = mapped_column(Text, nullable=True)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    entry: Mapped[SkillMarketplaceEntry] = relationship(
        "SkillMarketplaceEntry", back_populates="ratings", lazy="selectin"
    )


class CalendarConnection(Base):
    """A user's connected calendar (Google or Microsoft)."""

    __tablename__ = "calendar_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class Map(Base):
    """A custom office map stored as TMJ (Tiled Map JSON)."""

    __tablename__ = "maps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    tmj_content: Mapped[str] = mapped_column(Text, nullable=False)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class TaskEvent(Base):
    """INSERT-only event record for full-stack task observability."""

    __tablename__ = "task_events"
    __table_args__ = (
        Index("ix_task_events_task_created", "task_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("swarm_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    graph_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChatMessage(Base):
    """A persistent chat message in a room."""

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    room_id: Mapped[str] = mapped_column(String(100), nullable=False)
    sender_session_id: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    sender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="default", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ---------------------------------------------------------------------------
# Wave 4 models (Gap 2: Command Approvals, Gap 3: Cron Scheduler)
# ---------------------------------------------------------------------------


class ApprovalStatus(enum.StrEnum):
    """Status for dangerous-command approval requests."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class CommandApprovalRequest(Base):
    """Approval gate for dangerous commands detected by the ACP QA Oracle."""

    __tablename__ = "command_approval_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


class ScheduledAction(enum.StrEnum):
    """Actions that can be scheduled via cron expressions."""

    ACP_INITIATE = "acp_initiate"
    SKILL_REFINE = "skill_refine"
    MEMORY_COMPACT = "memory_compact"


class Schedule(Base):
    """A user-defined recurring schedule executed by Celery Beat."""

    __tablename__ = "schedules"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    cron_expr: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[ScheduledAction] = mapped_column(Enum(ScheduledAction), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Multi-tenant enterprise provisioning (migration 0015)
# ---------------------------------------------------------------------------


class TenantConfig(Base):
    """Per-organization configuration for multi-tenant operations.

    Stores business identity (RFC, razon social), localization preferences,
    ecosystem integration references (Karafiel, Dhanam, Phyne), feature
    flags, and resource limits.
    """

    __tablename__ = "tenant_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    org_id: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    # Business identity
    rfc: Mapped[str | None] = mapped_column(String(13), nullable=True)
    razon_social: Mapped[str | None] = mapped_column(String(500), nullable=True)
    regimen_fiscal: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Localization
    locale: Mapped[str] = mapped_column(String(10), nullable=False, default="es-MX")
    timezone: Mapped[str] = mapped_column(
        String(50), nullable=False, default="America/Mexico_City"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="MXN")

    # Ecosystem integration references
    karafiel_org_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dhanam_space_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phyne_tenant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Feature flags
    cfdi_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    intelligence_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Resource limits
    max_agents: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    max_daily_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    # Enterprise SSO (migration 0016)
    janua_connection_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # White-label branding (migration 0016)
    brand_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brand_logo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    brand_primary_color: Mapped[str | None] = mapped_column(
        String(7), nullable=True
    )  # hex e.g. #4a9e6e

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


# ---------------------------------------------------------------------------
# Audit trail (migration 0017)
# ---------------------------------------------------------------------------


class AuditLog(Base):
    """Immutable audit log for state-changing API actions.

    Every POST, PUT, PATCH, DELETE request that reaches a 2xx response is
    recorded with the authenticated user, resource path, and action details.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_org_created", "org_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    org_id: Mapped[str] = mapped_column(
        String(255), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # POST, PUT, PATCH, DELETE
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow
    )


# ---------------------------------------------------------------------------
# HITL Confidence (Sprint 1 — observe only)
# ---------------------------------------------------------------------------
#
# The HITL confidence system tracks approve/modify/reject decisions per
# (agent, action_category, org, context_signature) bucket so that — in
# later sprints — policy can widen autonomy for buckets with sustained
# high approval rates. Sprint 1 is observe-only: we record decisions and
# roll them into `hitl_confidence` but never change the permission engine's
# behaviour. See the design doc for the promotion ladder and thresholds.


class HitlOutcome(enum.StrEnum):
    """Terminal outcomes for a HITL decision.

    Order matters for the Beta posterior update:
        approved_clean      → α += 1.0  (full trust signal)
        approved_modified   → α += 0.3, β += 0.7  (partial rejection)
        rejected            → β += 1.0
        timeout             → β += 0.5  (silence ≠ approval)
        downstream_reverted → β += 2.0  (loud negative; demotes buckets)
    """

    APPROVED_CLEAN = "approved_clean"
    APPROVED_MODIFIED = "approved_modified"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    DOWNSTREAM_REVERTED = "downstream_reverted"


class HitlConfidenceTier(enum.StrEnum):
    """Promotion ladder. Sprint 1 only ever assigns ASK."""

    ASK = "ask"
    ASK_QUIET = "ask_quiet"
    ALLOW_SHADOW = "allow_shadow"
    ALLOW = "allow"


class HitlDecision(Base):
    """Append-only event log for every HITL decision.

    Primary source of truth — `hitl_confidence` is derived from this
    table and can always be rebuilt. Rows are never updated or deleted;
    downstream signals (revert / complaint) appear as new rows that
    reference the original via ``parent_decision_id``.
    """

    __tablename__ = "hitl_decisions"
    __table_args__ = (
        Index("ix_hitl_decisions_bucket_decided", "bucket_key", "decided_at"),
        Index("ix_hitl_decisions_agent_cat", "agent_id", "action_category"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_new_uuid
    )
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    # Pre-computed sha256 of agent_id:action_category:org_id:context_signature.
    # Used as the join key to `hitl_confidence`.
    bucket_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action_category: Mapped[str] = mapped_column(String(50), nullable=False)
    org_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    context_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    context_signature_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    approver_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[HitlOutcome] = mapped_column(Enum(HitlOutcome), nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Hashes — never the raw payload, so the audit trail is PII-free even
    # when rebuilt or replicated. Investigators follow the hash back to
    # the primary request store if they need the text.
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diff_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Reference to the original decision when this row is a downstream
    # signal (revert / complaint). Null for the primary approve/deny row.
    parent_decision_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hitl_decisions.id"), nullable=True
    )

    # Free-form annotation by the approver (optional). Capped at 500 chars.
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class HitlConfidence(Base):
    """Rolling per-bucket confidence state.

    Incrementally updated on every write to `hitl_decisions`. The Beta
    distribution shape (α, β) is the canonical posterior; `confidence`
    is the mean (α / (α+β)) cached for fast dashboard reads. Tier stays
    ``ASK`` throughout Sprint 1 — promotion logic lands in Sprint 2.
    """

    __tablename__ = "hitl_confidence"
    __table_args__ = (
        Index("ix_hitl_confidence_agent_cat", "agent_id", "action_category"),
    )

    bucket_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action_category: Mapped[str] = mapped_column(String(50), nullable=False)
    org_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    context_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    context_signature_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )

    n_observed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_approved_clean: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_approved_modified: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    n_rejected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_timeout: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    n_reverted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Beta posterior — starts at (1.0, 1.0) for an uninformative prior.
    beta_alpha: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    beta_beta: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Cached mean = alpha / (alpha + beta). Recomputed on every update.
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)

    tier: Mapped[HitlConfidenceTier] = mapped_column(
        Enum(HitlConfidenceTier),
        nullable=False,
        default=HitlConfidenceTier.ASK,
    )
    last_promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # When a revert/complaint fires we set `locked_until` and refuse to
    # promote past the current tier until the lock clears. Sprint 1 never
    # writes this field — kept on the model so Sprint 2 can use it.
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_decision_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )
