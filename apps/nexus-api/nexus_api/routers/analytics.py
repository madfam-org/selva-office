"""Analytics API -- sales pipeline, accounting close, intelligence briefing summary."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import get_db
from ..models import SwarmTask, TaskEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])


# -- Response models ----------------------------------------------------------


class SalesPipelineMetrics(BaseModel):
    total_leads: int = 0
    active_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    avg_duration_seconds: float | None = None
    period: str = ""


class AccountingCloseStatus(BaseModel):
    period: str = ""
    total_accounting_tasks: int = 0
    completed: int = 0
    pending: int = 0
    failed: int = 0
    last_completed_at: str | None = None


class IntelligenceSummary(BaseModel):
    total_briefings: int = 0
    last_briefing_at: str | None = None
    dof_entries_scanned: int = 0
    indicators_fetched: int = 0
    period: str = ""


# -- Endpoints ----------------------------------------------------------------


@router.get("/sales", response_model=SalesPipelineMetrics)
async def sales_pipeline_metrics(
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    period: str = Query(
        "30d",
        description="Time period: 1d, 7d, 30d, 90d",
        pattern=r"^(1d|7d|30d|90d)$",
    ),
) -> SalesPipelineMetrics:
    """Sales pipeline metrics: task counts and average duration for sales graph."""
    org_id = getattr(user, "org_id", "default")
    cutoff = _period_to_cutoff(period)

    query = (
        select(
            func.count().label("total"),
            func.count().filter(SwarmTask.status == "running").label("active"),
            func.count().filter(SwarmTask.status == "completed").label("completed"),
            func.count().filter(SwarmTask.status == "failed").label("failed"),
        )
        .where(SwarmTask.org_id == org_id)
        .where(SwarmTask.graph_type == "sales")
        .where(SwarmTask.created_at >= cutoff)
    )

    result = await db.execute(query)
    row = result.one()

    # Calculate average duration from events
    avg_query = (
        select(func.avg(TaskEvent.duration_ms))
        .where(TaskEvent.org_id == org_id)
        .where(TaskEvent.graph_type == "sales")
        .where(TaskEvent.event_type == "task.completed")
        .where(TaskEvent.created_at >= cutoff)
    )
    avg_result = await db.execute(avg_query)
    avg_ms = avg_result.scalar_one_or_none()

    return SalesPipelineMetrics(
        total_leads=row.total,
        active_tasks=row.active,
        completed_tasks=row.completed,
        failed_tasks=row.failed,
        avg_duration_seconds=round(avg_ms / 1000, 2) if avg_ms else None,
        period=period,
    )


@router.get("/accounting", response_model=AccountingCloseStatus)
async def accounting_close_status(
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    period: str = Query(
        "30d",
        description="Time period: 1d, 7d, 30d, 90d",
        pattern=r"^(1d|7d|30d|90d)$",
    ),
) -> AccountingCloseStatus:
    """Accounting monthly close status: task progress for accounting graph."""
    org_id = getattr(user, "org_id", "default")
    cutoff = _period_to_cutoff(period)

    query = (
        select(
            func.count().label("total"),
            func.count().filter(SwarmTask.status == "completed").label("completed"),
            func.count()
            .filter(SwarmTask.status.in_(["queued", "pending", "running"]))
            .label("pending"),
            func.count().filter(SwarmTask.status == "failed").label("failed"),
            func.max(SwarmTask.completed_at).label("last_completed"),
        )
        .where(SwarmTask.org_id == org_id)
        .where(SwarmTask.graph_type.in_(["accounting", "billing"]))
        .where(SwarmTask.created_at >= cutoff)
    )

    result = await db.execute(query)
    row = result.one()

    return AccountingCloseStatus(
        period=period,
        total_accounting_tasks=row.total,
        completed=row.completed,
        pending=row.pending,
        failed=row.failed,
        last_completed_at=(row.last_completed.isoformat() if row.last_completed else None),
    )


@router.get("/intelligence", response_model=IntelligenceSummary)
async def intelligence_summary(
    user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    period: str = Query(
        "30d",
        description="Time period: 1d, 7d, 30d, 90d",
        pattern=r"^(1d|7d|30d|90d)$",
    ),
) -> IntelligenceSummary:
    """Intelligence briefing summary: count of briefings and data points."""
    org_id = getattr(user, "org_id", "default")
    cutoff = _period_to_cutoff(period)

    # Count completed intelligence tasks
    task_query = (
        select(
            func.count().label("total"),
            func.max(SwarmTask.completed_at).label("last_completed"),
        )
        .where(SwarmTask.org_id == org_id)
        .where(SwarmTask.graph_type == "intelligence")
        .where(SwarmTask.status == "completed")
        .where(SwarmTask.created_at >= cutoff)
    )
    task_result = await db.execute(task_query)
    task_row = task_result.one()

    # Count intelligence-related events for data point metrics
    event_query = (
        select(func.count())
        .where(TaskEvent.org_id == org_id)
        .where(TaskEvent.graph_type == "intelligence")
        .where(TaskEvent.created_at >= cutoff)
    )
    event_result = await db.execute(event_query)
    event_count = event_result.scalar_one()

    return IntelligenceSummary(
        total_briefings=task_row.total,
        last_briefing_at=(task_row.last_completed.isoformat() if task_row.last_completed else None),
        dof_entries_scanned=event_count,  # Approximation from events
        indicators_fetched=event_count,
        period=period,
    )


# -- Helpers ------------------------------------------------------------------


def _period_to_cutoff(period: str) -> datetime:
    """Convert a period string to a cutoff datetime."""
    mapping = {
        "1d": timedelta(days=1),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
        "90d": timedelta(days=90),
    }
    delta = mapping.get(period, timedelta(days=30))
    return datetime.now(UTC) - delta
