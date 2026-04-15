"""
Gap 2: ApprovalRequest SQLAlchemy model.
"""
from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, Enum, String, Text

from ..database import Base


class ApprovalStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    EXPIRED = "expired"


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: str = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    run_id: str = Column(String(255), nullable=False, index=True)
    command: str = Column(Text, nullable=False)
    reason: str = Column(Text, nullable=False)
    status: ApprovalStatus = Column(
        Enum(ApprovalStatus), nullable=False, default=ApprovalStatus.PENDING,
    )
    requested_at: datetime = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(tz=UTC),
    )
    resolved_at: datetime = Column(DateTime(timezone=True), nullable=True)
    resolved_by: str = Column(String(255), nullable=True)
