"""Ops metrics dashboard aggregation API."""

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
from ..models import ApprovalRequest, ComputeTokenLedger, SwarmTask, TaskEvent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"], dependencies=[Depends(get_current_user)])

PERIOD_MAP: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


class TrendPoint(BaseModel):
    timestamp: str
    value: float


class MetricsDashboardResponse(BaseModel):
    period: str
    agent_utilization_pct: float
    task_throughput: dict[str, Any]
    approval_latency: dict[str, Any]
    cost_breakdown: list[dict[str, Any]]
    error_rate: float
    trends: dict[str, list[TrendPoint]]
    recent_errors: list[dict[str, Any]]


@router.get("/dashboard", response_model=MetricsDashboardResponse)
async def get_metrics_dashboard(
    period: str = Query(default="24h", pattern=r"^(1h|6h|24h|7d|30d)$"),
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> MetricsDashboardResponse:
    """Return aggregated ops metrics for the dashboard."""
    delta = PERIOD_MAP[period]
    since = datetime.now(UTC) - delta

    # -- Agent utilization % --------------------------------------------------
    # Sum of node durations per agent / wall time
    util_result = await db.execute(
        select(func.sum(TaskEvent.duration_ms))
        .where(TaskEvent.created_at >= since)
        .where(TaskEvent.event_category == "node")
        .where(TaskEvent.duration_ms.isnot(None))
    )
    total_node_ms: int = util_result.scalar_one() or 0

    agent_count_result = await db.execute(
        select(func.count(func.distinct(TaskEvent.agent_id)))
        .where(TaskEvent.created_at >= since)
        .where(TaskEvent.agent_id.isnot(None))
    )
    active_agents: int = agent_count_result.scalar_one() or 1

    wall_ms = delta.total_seconds() * 1000
    utilization = min(
        100.0,
        (total_node_ms / (wall_ms * max(active_agents, 1))) * 100,
    )

    # -- Task throughput ------------------------------------------------------
    throughput_result = await db.execute(
        select(
            SwarmTask.status,
            func.count(SwarmTask.id),
        )
        .where(SwarmTask.created_at >= since)
        .group_by(SwarmTask.status)
    )
    status_counts: dict[str, int] = {}
    for row in throughput_result:
        status_counts[row[0]] = row[1]

    duration_result = await db.execute(
        select(
            func.avg(
                func.extract("epoch", SwarmTask.completed_at)
                - func.extract("epoch", SwarmTask.started_at)
            ),
        )
        .where(SwarmTask.created_at >= since)
        .where(SwarmTask.completed_at.isnot(None))
        .where(SwarmTask.started_at.isnot(None))
    )
    avg_duration_s = duration_result.scalar_one()

    task_throughput = {
        "status_counts": status_counts,
        "total": sum(status_counts.values()),
        "avg_duration_s": round(avg_duration_s, 1) if avg_duration_s else None,
    }

    # -- Approval latency -----------------------------------------------------
    approval_agg = await db.execute(
        select(
            func.avg(
                func.extract("epoch", ApprovalRequest.responded_at)
                - func.extract("epoch", ApprovalRequest.created_at)
            ),
            func.count(ApprovalRequest.id),
        )
        .where(ApprovalRequest.created_at >= since)
        .where(ApprovalRequest.responded_at.isnot(None))
    )
    agg_row = approval_agg.one()
    avg_approval_s = agg_row[0]
    resolved_count = agg_row[1]

    pending_count_result = await db.execute(
        select(func.count(ApprovalRequest.id))
        .where(ApprovalRequest.status == "pending")
    )
    pending_count = pending_count_result.scalar_one() or 0

    approval_latency = {
        "avg_seconds": round(avg_approval_s, 1) if avg_approval_s else None,
        "resolved_count": resolved_count,
        "pending_count": pending_count,
    }

    # -- Cost breakdown -------------------------------------------------------
    cost_result = await db.execute(
        select(
            ComputeTokenLedger.provider,
            ComputeTokenLedger.model,
            func.sum(ComputeTokenLedger.amount),
            func.count(ComputeTokenLedger.id),
        )
        .where(ComputeTokenLedger.created_at >= since)
        .group_by(ComputeTokenLedger.provider, ComputeTokenLedger.model)
        .order_by(func.sum(ComputeTokenLedger.amount).desc())
    )
    cost_breakdown = [
        {
            "provider": row[0] or "unknown",
            "model": row[1] or "unknown",
            "total_tokens": row[2],
            "call_count": row[3],
        }
        for row in cost_result
    ]

    # -- Error rate -----------------------------------------------------------
    total_events_result = await db.execute(
        select(func.count(TaskEvent.id))
        .where(TaskEvent.created_at >= since)
    )
    total_events = total_events_result.scalar_one() or 1

    error_events_result = await db.execute(
        select(func.count(TaskEvent.id))
        .where(TaskEvent.created_at >= since)
        .where(TaskEvent.event_type.in_(["task.failed", "task.timeout", "node.error"]))
    )
    error_events = error_events_result.scalar_one() or 0
    error_rate = (error_events / max(total_events, 1)) * 100

    # -- Trend sparklines (hourly buckets) ------------------------------------
    trends: dict[str, list[TrendPoint]] = {"tasks": [], "errors": []}

    bucket_hours = max(1, int(delta.total_seconds() / 3600 / 24))
    bucket_interval = timedelta(hours=bucket_hours)
    cursor = since
    while cursor < datetime.now(UTC):
        bucket_end = cursor + bucket_interval

        task_count_result = await db.execute(
            select(func.count(SwarmTask.id))
            .where(SwarmTask.created_at >= cursor)
            .where(SwarmTask.created_at < bucket_end)
        )
        trends["tasks"].append(TrendPoint(
            timestamp=cursor.isoformat(),
            value=float(task_count_result.scalar_one() or 0),
        ))

        err_count_result = await db.execute(
            select(func.count(TaskEvent.id))
            .where(TaskEvent.created_at >= cursor)
            .where(TaskEvent.created_at < bucket_end)
            .where(TaskEvent.event_type.in_(["task.failed", "node.error"]))
        )
        trends["errors"].append(TrendPoint(
            timestamp=cursor.isoformat(),
            value=float(err_count_result.scalar_one() or 0),
        ))

        cursor = bucket_end

    # -- Recent errors --------------------------------------------------------
    recent_errors_result = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.created_at >= since)
        .where(TaskEvent.event_type.in_(["task.failed", "task.timeout", "node.error"]))
        .order_by(TaskEvent.created_at.desc())
        .limit(10)
    )
    recent_errors = [
        {
            "id": str(e.id),
            "task_id": str(e.task_id) if e.task_id else None,
            "event_type": e.event_type,
            "node_id": e.node_id,
            "error_message": e.error_message,
            "created_at": e.created_at.isoformat(),
        }
        for e in recent_errors_result.scalars()
    ]

    return MetricsDashboardResponse(
        period=period,
        agent_utilization_pct=round(utilization, 1),
        task_throughput=task_throughput,
        approval_latency=approval_latency,
        cost_breakdown=cost_breakdown,
        error_rate=round(error_rate, 2),
        trends=trends,
        recent_errors=recent_errors,
    )
