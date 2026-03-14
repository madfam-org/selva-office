"""Swarm task dispatch and monitoring endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autoswarm_redis_pool import get_redis_pool

from ..auth import get_current_user
from ..config import get_settings
from ..database import get_db
from ..models import Agent, ComputeTokenLedger, SwarmTask, Workflow
from ..tenant import TenantContext, get_tenant

router = APIRouter(tags=["swarms"], dependencies=[Depends(get_current_user)])


# -- Request / Response schemas -----------------------------------------------


class DispatchRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2000)
    graph_type: str = Field(
        default="sequential",
        pattern=r"^(sequential|parallel|coding|research|crm|custom|deployment|puppeteer|meeting)$",
    )
    assigned_agent_ids: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = Field(
        default=None,
        description="UUID of a custom workflow definition (required for graph_type='custom')",
    )


class SwarmTaskResponse(BaseModel):
    id: str
    description: str
    graph_type: str
    assigned_agent_ids: list[str]
    payload: dict[str, Any]
    status: str
    created_at: str
    completed_at: str | None

    model_config = {"from_attributes": True}


class TaskStatusUpdate(BaseModel):
    status: str = Field(..., pattern=r"^(running|completed|failed|cancelled)$")
    result: dict[str, Any] | None = None
    started_at: str | None = None
    error_message: str | None = None


# -- Helpers ------------------------------------------------------------------


def _task_to_response(task: SwarmTask) -> SwarmTaskResponse:
    return SwarmTaskResponse(
        id=str(task.id),
        description=task.description,
        graph_type=task.graph_type,
        assigned_agent_ids=task.assigned_agent_ids or [],
        payload=task.payload or {},
        status=task.status,
        created_at=task.created_at.isoformat(),
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
    )


# -- Endpoints ----------------------------------------------------------------


@router.post("/dispatch", response_model=SwarmTaskResponse, status_code=status.HTTP_201_CREATED)
async def dispatch_task(
    body: DispatchRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    tenant: TenantContext = Depends(get_tenant),  # noqa: B008
) -> SwarmTaskResponse:
    """Dispatch a new swarm task.

    Validates compute token budget, persists the task, and publishes a
    message to the Redis task queue for worker consumption.
    """
    settings = get_settings()

    # Extract request_id for cross-service correlation.
    request_id = getattr(request.state, "request_id", None)

    # -- Validate custom workflow dispatch ------------------------------------
    workflow_yaml: str | None = None
    if body.graph_type == "custom":
        if not body.workflow_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="workflow_id is required when graph_type is 'custom'",
            )
        try:
            wf_uid = uuid.UUID(body.workflow_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid workflow_id UUID",
            ) from exc
        wf_result = await db.execute(select(Workflow).where(Workflow.id == wf_uid))
        wf = wf_result.scalar_one_or_none()
        if wf is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found",
            )
        workflow_yaml = wf.yaml_content

    # -- Skill-based agent matching (when no explicit agents provided) --------
    assigned_agent_ids = body.assigned_agent_ids
    if not assigned_agent_ids and body.required_skills:
        # Auto-select agents by skill overlap
        try:
            from autoswarm_skills import DEFAULT_ROLE_SKILLS

            result = await db.execute(
                select(Agent).where(Agent.status == "idle").order_by(Agent.created_at)
            )
            idle_agents = result.scalars().all()
            scored: list[tuple[float, Any]] = []
            required = set(body.required_skills)
            for agent in idle_agents:
                agent_skills = set(
                    agent.skill_ids or DEFAULT_ROLE_SKILLS.get(agent.role, [])
                )
                overlap = len(required & agent_skills)
                if overlap > 0:
                    scored.append((overlap / len(required), agent))
            scored.sort(key=lambda x: x[0], reverse=True)
            assigned_agent_ids = [str(a.id) for _, a in scored[:3]]
        except Exception:
            pass  # Fall through to dispatch without auto-selection

    # -- Compute token budget check -------------------------------------------
    dispatch_cost = 10  # matches ComputeTokenManager.COST_TABLE["dispatch_task"]

    # Check remaining budget before dispatching.
    today_start = datetime.now(UTC).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    budget_result = await db.execute(
        select(func.coalesce(func.sum(ComputeTokenLedger.amount), 0)).where(
            ComputeTokenLedger.created_at >= today_start,
            ComputeTokenLedger.org_id == tenant.org_id,
        )
    )
    used: int = budget_result.scalar_one()
    daily_limit = 1000  # Default; production reads from Redis tier cache
    if used + dispatch_cost > daily_limit:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Compute token budget exceeded for today",
        )

    # Record the debit in the ledger (the in-memory ComputeTokenManager lives
    # in the orchestrator package; the ledger is the durable record).
    wf_uid_value = wf_uid if body.graph_type == "custom" else None
    task = SwarmTask(
        description=body.description,
        graph_type=body.graph_type,
        assigned_agent_ids=assigned_agent_ids,
        payload=body.payload,
        status="queued",
        org_id=tenant.org_id,
        workflow_id=wf_uid_value,
    )
    db.add(task)
    await db.flush()
    await db.refresh(task)

    ledger_entry = ComputeTokenLedger(
        action="dispatch_task",
        amount=dispatch_cost,
        task_id=task.id,
        org_id=tenant.org_id,
    )
    db.add(ledger_entry)
    await db.flush()

    # -- Publish to Redis queue for workers -----------------------------------
    try:
        pool = get_redis_pool(url=settings.redis_url)
        task_msg_data: dict[str, Any] = {
            "task_id": str(task.id),
            "graph_type": task.graph_type,
            "description": task.description,
            "assigned_agent_ids": task.assigned_agent_ids,
            "required_skills": body.required_skills,
            "payload": task.payload,
            "request_id": request_id,
        }
        if workflow_yaml is not None:
            task_msg_data["workflow_yaml"] = workflow_yaml
        task_msg = json.dumps(task_msg_data)
        # Dual-write: LPUSH (legacy) + XADD (stream) for migration
        await pool.execute_with_retry("lpush", "autoswarm:tasks", task_msg)
        await pool.execute_with_retry("xadd", "autoswarm:task-stream", {"data": task_msg})
    except Exception:
        # If Redis is unavailable the task is still persisted in the DB.
        # Workers can fall back to polling the database.
        task.status = "pending"
        await db.flush()

    return _task_to_response(task)


@router.get("/tasks", response_model=list[SwarmTaskResponse])
async def list_active_tasks(
    db: AsyncSession = Depends(get_db),  # noqa: B008
    tenant: TenantContext = Depends(get_tenant),  # noqa: B008
) -> list[SwarmTaskResponse]:
    """List tasks that are currently queued or in progress."""
    result = await db.execute(
        select(SwarmTask)
        .where(SwarmTask.status.in_(["queued", "pending", "running"]))
        .where(SwarmTask.org_id == tenant.org_id)
        .order_by(SwarmTask.created_at.desc())
    )
    tasks = result.scalars().all()
    return [_task_to_response(t) for t in tasks]


@router.get("/tasks/{task_id}", response_model=SwarmTaskResponse)
async def get_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> SwarmTaskResponse:
    """Retrieve a single task by ID."""
    try:
        uid = uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID"
        ) from exc

    result = await db.execute(select(SwarmTask).where(SwarmTask.id == uid))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )
    return _task_to_response(task)


@router.patch("/tasks/{task_id}", response_model=SwarmTaskResponse)
async def update_task_status(
    task_id: str,
    body: TaskStatusUpdate,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> SwarmTaskResponse:
    """Update a task's status.

    When the status transitions to ``completed`` or ``failed`` the
    ``completed_at`` timestamp is set automatically.
    """
    try:
        uid = uuid.UUID(task_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID"
        ) from exc

    result = await db.execute(select(SwarmTask).where(SwarmTask.id == uid))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task not found"
        )

    task.status = body.status

    if body.result is not None:
        task.payload = {**(task.payload or {}), "result": body.result}

    if body.started_at is not None:
        task.started_at = datetime.fromisoformat(body.started_at)

    if body.error_message is not None:
        task.error_message = body.error_message

    if body.status in ("completed", "failed"):
        task.completed_at = datetime.now(UTC)

    await db.flush()
    await db.refresh(task)

    return _task_to_response(task)
