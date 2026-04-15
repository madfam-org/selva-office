"""
Gap 2: Command Approvals REST router.

Allows operators to view pending dangerous command approval requests and
resolve them from the API, UI, or any connected gateway channel.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import CurrentUser, require_roles
from ..database import get_db
from ..models import ApprovalStatus
from ..models import CommandApprovalRequest as ApprovalRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/command-approvals", tags=["Command Approvals"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ApprovalRequestResponse(BaseModel):
    id: str
    run_id: str
    command: str
    reason: str
    status: ApprovalStatus
    requested_at: str
    resolved_at: str | None
    resolved_by: str | None

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/pending", response_model=list[ApprovalRequestResponse])
async def list_pending(
    user: CurrentUser = Depends(require_roles(["admin", "enterprise-cleanroom"])),
    db: AsyncSession = Depends(get_db),
) -> list[ApprovalRequestResponse]:
    """List all pending dangerous command approval requests."""
    result = await db.execute(
        select(ApprovalRequest)
        .where(ApprovalRequest.status == ApprovalStatus.PENDING)
        .order_by(ApprovalRequest.requested_at.desc())
    )
    return [_to_schema(r) for r in result.scalars().all()]


@router.post("/{request_id}/approve", response_model=ApprovalRequestResponse)
async def approve_command(
    request_id: str,
    user: CurrentUser = Depends(require_roles(["admin", "enterprise-cleanroom"])),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestResponse:
    """Approve a pending dangerous command."""
    return await _resolve(request_id, approved=True, user=user, db=db)


@router.post("/{request_id}/deny", response_model=ApprovalRequestResponse)
async def deny_command(
    request_id: str,
    user: CurrentUser = Depends(require_roles(["admin", "enterprise-cleanroom"])),
    db: AsyncSession = Depends(get_db),
) -> ApprovalRequestResponse:
    """Deny a pending dangerous command."""
    return await _resolve(request_id, approved=False, user=user, db=db)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _resolve(
    request_id: str, approved: bool, user: CurrentUser, db: AsyncSession
) -> ApprovalRequestResponse:
    req = await db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Approval request not found")
    if req.status != ApprovalStatus.PENDING:
        raise HTTPException(status_code=409, detail=f"Request already {req.status}")

    req.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.DENIED
    req.resolved_at = datetime.now(tz=UTC)
    req.resolved_by = user.sub
    await db.commit()
    await db.refresh(req)

    # Notify the in-process approval store
    from autoswarm_tools.approval import resolve_approval
    resolve_approval(request_id, approved, resolved_by=user.sub)

    logger.info("Approval %s %s by %s", request_id, req.status, user.sub)
    return _to_schema(req)


def _to_schema(r: ApprovalRequest) -> ApprovalRequestResponse:
    return ApprovalRequestResponse(
        id=r.id,
        run_id=r.run_id,
        command=r.command,
        reason=r.reason,
        status=r.status,
        requested_at=r.requested_at.isoformat() if r.requested_at else "",
        resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
        resolved_by=r.resolved_by,
    )
