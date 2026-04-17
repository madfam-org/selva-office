"""
Schedule model — Gap 3: Cron Scheduler Integration.

Persists user-defined schedules in Postgres so Celery Beat can
dynamically fire recurring Selva actions (ACP runs, skill refinement,
memory compaction, etc.) without any dashboard interaction.
"""
from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from ..database import Base


class ScheduledAction(enum.StrEnum):
    ACP_INITIATE = "acp_initiate"
    SKILL_REFINE = "skill_refine"
    MEMORY_COMPACT = "memory_compact"


class Schedule(Base):
    """
    A user-defined recurring schedule.

    ``cron_expr`` follows standard 5-field crontab syntax: minute hour day month weekday.
    ``payload`` stores action-specific parameters (e.g., target_url for acp_initiate).
    """

    __tablename__ = "schedules"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: str = Column(String(255), nullable=False, index=True)
    cron_expr: str = Column(String(100), nullable=False)
    action: ScheduledAction = Column(Enum(ScheduledAction), nullable=False)
    payload: dict = Column(JSONB, nullable=False, default=dict)
    enabled: bool = Column(Boolean, nullable=False, default=True)
    description: str = Column(Text, nullable=True)
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=UTC),
    )
    last_run_at: datetime = Column(DateTime(timezone=True), nullable=True)
