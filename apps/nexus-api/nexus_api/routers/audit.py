"""Audit trail API -- query and export audit logs (admin only)."""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


class AuditLogResponse(BaseModel):
    id: str
    org_id: str
    user_id: str
    action: str
    resource_type: str
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    created_at: str


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


def _require_admin(user: Any) -> None:
    """Raise 403 if the user is not an admin."""
    roles = getattr(user, "roles", []) or []
    if "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required to access audit logs",
        )


@router.get("/", response_model=AuditLogListResponse)
async def list_audit_logs(
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: str | None = Query(None, description="Filter by HTTP method"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    user_id: str | None = Query(None, description="Filter by user ID"),
    since: str | None = Query(None, description="Filter after ISO datetime"),
    until: str | None = Query(None, description="Filter before ISO datetime"),
) -> AuditLogListResponse:
    """List audit logs with pagination and optional filters. Admin only."""
    _require_admin(user)

    org_id = getattr(user, "org_id", "default")
    query = select(AuditLog).where(AuditLog.org_id == org_id)

    if action:
        query = query.where(AuditLog.action == action.upper())
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.where(AuditLog.created_at >= since_dt)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid since format: {since}",
            ) from exc
    if until:
        try:
            until_dt = datetime.fromisoformat(until)
            query = query.where(AuditLog.created_at <= until_dt)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid until format: {until}",
            ) from exc

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Fetch page
    offset = (page - 1) * page_size
    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(query)
    logs = result.scalars().all()

    items = [
        AuditLogResponse(
            id=str(log.id),
            org_id=log.org_id,
            user_id=log.user_id,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=log.resource_id,
            details=log.details,
            ip_address=log.ip_address,
            created_at=log.created_at.isoformat(),
        )
        for log in logs
    ]

    return AuditLogListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/export")
async def export_audit_logs(
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    since: str | None = Query(None, description="Filter after ISO datetime"),
    until: str | None = Query(None, description="Filter before ISO datetime"),
    action: str | None = Query(None, description="Filter by HTTP method"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
) -> Any:
    """Export audit logs as CSV. Admin only. Max 10,000 rows."""
    from starlette.responses import StreamingResponse

    _require_admin(user)

    org_id = getattr(user, "org_id", "default")
    query = select(AuditLog).where(AuditLog.org_id == org_id)

    if action:
        query = query.where(AuditLog.action == action.upper())
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.where(AuditLog.created_at >= since_dt)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid since format: {since}",
            ) from exc
    if until:
        try:
            until_dt = datetime.fromisoformat(until)
            query = query.where(AuditLog.created_at <= until_dt)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid until format: {until}",
            ) from exc

    query = query.order_by(AuditLog.created_at.desc()).limit(10_000)
    result = await db.execute(query)
    logs = result.scalars().all()

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "org_id", "user_id", "action", "resource_type",
        "resource_id", "ip_address", "created_at", "details",
    ])
    for log in logs:
        writer.writerow([
            str(log.id),
            log.org_id,
            log.user_id,
            log.action,
            log.resource_type,
            log.resource_id or "",
            log.ip_address or "",
            log.created_at.isoformat(),
            str(log.details or ""),
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )
