"""Task event observability endpoints -- REST + WebSocket stream."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import get_current_user
from ..database import async_session_factory, get_db
from ..models import TaskEvent
from ..ws import MessageRateLimiter, event_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])

_ws_rate_limiter = MessageRateLimiter(max_messages=30, window_seconds=60.0)


# -- Request / Response schemas -----------------------------------------------


class CreateEventRequest(BaseModel):
    event_type: str = Field(..., max_length=50)
    event_category: str = Field(..., max_length=50)
    task_id: str | None = None
    agent_id: str | None = None
    node_id: str | None = None
    graph_type: str | None = None
    payload: dict[str, Any] | None = None
    duration_ms: int | None = None
    provider: str | None = None
    model: str | None = None
    token_count: int | None = None
    error_message: str | None = None
    request_id: str | None = None
    org_id: str = "default"


class TaskEventResponse(BaseModel):
    id: str
    task_id: str | None
    agent_id: str | None
    event_type: str
    event_category: str
    node_id: str | None
    graph_type: str | None
    payload: dict[str, Any] | None
    duration_ms: int | None
    provider: str | None
    model: str | None
    token_count: int | None
    error_message: str | None
    request_id: str | None
    org_id: str
    created_at: str

    model_config = {"from_attributes": True}


class TimelineResponse(BaseModel):
    task_id: str
    events: list[TaskEventResponse]
    total_duration_ms: int | None
    total_tokens: int | None


# -- Helpers ------------------------------------------------------------------


def _event_to_response(ev: TaskEvent) -> TaskEventResponse:
    return TaskEventResponse(
        id=str(ev.id),
        task_id=str(ev.task_id) if ev.task_id else None,
        agent_id=str(ev.agent_id) if ev.agent_id else None,
        event_type=ev.event_type,
        event_category=ev.event_category,
        node_id=ev.node_id,
        graph_type=ev.graph_type,
        payload=ev.payload,
        duration_ms=ev.duration_ms,
        provider=ev.provider,
        model=ev.model,
        token_count=ev.token_count,
        error_message=ev.error_message,
        request_id=ev.request_id,
        org_id=ev.org_id,
        created_at=ev.created_at.isoformat(),
    )


def _safe_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


# -- Endpoints ----------------------------------------------------------------


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_event(
    body: CreateEventRequest,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    """Create a new task event.

    Called by workers internally -- no authentication required (same
    pattern as POST /api/v1/approvals).
    """
    event = TaskEvent(
        task_id=_safe_uuid(body.task_id),
        agent_id=_safe_uuid(body.agent_id),
        event_type=body.event_type,
        event_category=body.event_category,
        node_id=body.node_id,
        graph_type=body.graph_type,
        payload=body.payload,
        duration_ms=body.duration_ms,
        provider=body.provider,
        model=body.model,
        token_count=body.token_count,
        error_message=body.error_message,
        request_id=body.request_id,
        org_id=body.org_id,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    # Broadcast to WebSocket clients
    response = _event_to_response(event)
    await event_manager.broadcast({"type": "task_event", "payload": response.model_dump()})

    return {"id": str(event.id)}


@router.get(
    "/",
    response_model=list[TaskEventResponse],
    dependencies=[Depends(get_current_user)],
)
async def list_events(
    task_id: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    event_category: str | None = Query(default=None),
    since: str | None = Query(default=None),
    until: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> list[TaskEventResponse]:
    """List events with optional filters, newest first."""
    query = select(TaskEvent).order_by(TaskEvent.created_at.desc())

    if task_id:
        uid = _safe_uuid(task_id)
        if uid:
            query = query.where(TaskEvent.task_id == uid)
    if agent_id:
        uid = _safe_uuid(agent_id)
        if uid:
            query = query.where(TaskEvent.agent_id == uid)
    if event_type:
        query = query.where(TaskEvent.event_type == event_type)
    if event_category:
        query = query.where(TaskEvent.event_category == event_category)
    if since:
        try:
            since_dt = datetime.fromisoformat(since)
            query = query.where(TaskEvent.created_at >= since_dt)
        except ValueError:
            pass
    if until:
        try:
            until_dt = datetime.fromisoformat(until)
            query = query.where(TaskEvent.created_at <= until_dt)
        except ValueError:
            pass

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    events = result.scalars().all()
    return [_event_to_response(e) for e in events]


@router.get(
    "/tasks/{task_id}/timeline",
    response_model=TimelineResponse,
    dependencies=[Depends(get_current_user)],
)
async def get_task_timeline(
    task_id: str,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> TimelineResponse:
    """Full execution timeline for a single task."""
    uid = _safe_uuid(task_id)
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid UUID"
        )

    result = await db.execute(
        select(TaskEvent)
        .where(TaskEvent.task_id == uid)
        .order_by(TaskEvent.created_at.asc())
    )
    events = result.scalars().all()

    # Aggregate duration and tokens
    agg = await db.execute(
        select(
            func.sum(TaskEvent.duration_ms),
            func.sum(TaskEvent.token_count),
        ).where(TaskEvent.task_id == uid)
    )
    row = agg.one()
    total_duration = row[0]
    total_tokens = row[1]

    return TimelineResponse(
        task_id=task_id,
        events=[_event_to_response(e) for e in events],
        total_duration_ms=total_duration,
        total_tokens=total_tokens,
    )


@router.websocket("/ws")
async def events_websocket(websocket: WebSocket) -> None:
    """Real-time event stream over WebSocket.

    On connect: sends last 50 events as ``event_batch``.
    Then relays new events from the ``autoswarm:events`` Redis channel.
    Same pattern as ``/api/v1/approvals/ws``.
    """
    client_id = websocket.query_params.get("client_id", str(uuid.uuid4()))
    await event_manager.connect(websocket, client_id)

    # Send initial batch
    try:
        async with async_session_factory() as session:
            result = await session.execute(
                select(TaskEvent)
                .order_by(TaskEvent.created_at.desc())
                .limit(50)
            )
            recent = result.scalars().all()
            batch = [_event_to_response(e).model_dump() for e in reversed(recent)]
            await websocket.send_json({"type": "event_batch", "payload": batch})
    except Exception:
        logger.warning("Failed to send initial event batch to client %s", client_id)

    try:
        while True:
            data = await websocket.receive_text()
            if not _ws_rate_limiter.check(client_id):
                await websocket.send_json({"type": "rate_limited"})
                continue
            if data == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        _ws_rate_limiter.remove(client_id)
        event_manager.disconnect(client_id)


# -- Direct DB event emission for server-side use ----------------------------


async def emit_event_db(
    db: AsyncSession,
    *,
    event_type: str,
    event_category: str,
    task_id: uuid.UUID | None = None,
    agent_id: uuid.UUID | None = None,
    **kwargs: Any,
) -> None:
    """Insert a TaskEvent directly (for server-side emission without HTTP).

    Fire-and-forget: exceptions are logged but never raised.
    """
    try:
        event = TaskEvent(
            task_id=task_id,
            agent_id=agent_id,
            event_type=event_type,
            event_category=event_category,
            **kwargs,
        )
        db.add(event)
        await db.flush()
        await db.refresh(event)

        response = _event_to_response(event)
        await event_manager.broadcast({"type": "task_event", "payload": response.model_dump()})
    except Exception:
        logger.warning("Failed to emit DB event %s", event_type, exc_info=True)
