"""Chat history API for persistent message storage.

Messages are written by the Colyseus server (fire-and-forget POST) and
read by clients to restore chat history on reconnection.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import ChatMessage
from ..tenant import TenantContext, get_tenant

router = APIRouter(tags=["chat"])


# -- Schemas ------------------------------------------------------------------


class ChatMessageCreate(BaseModel):
    room_id: str = Field(..., min_length=1, max_length=100)
    sender_session_id: str = Field(default="", max_length=100)
    sender_name: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=500)
    is_system: bool = False
    org_id: str = Field(default="default", max_length=255)


class ChatMessageResponse(BaseModel):
    id: str
    room_id: str
    sender_session_id: str
    sender_name: str
    content: str
    is_system: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# -- Endpoints ----------------------------------------------------------------


@router.get("/history", response_model=list[ChatMessageResponse])
async def get_chat_history(
    room_id: str = Query(..., min_length=1),  # noqa: B008
    limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
    before: datetime | None = Query(default=None),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    tenant: TenantContext = Depends(get_tenant),  # noqa: B008
) -> list[ChatMessageResponse]:
    """Return recent chat messages for a room, newest first.

    Pagination: pass ``before`` with the ``created_at`` of the oldest
    message in your current batch to fetch the next page.
    """
    query = (
        select(ChatMessage)
        .where(
            ChatMessage.room_id == room_id,
            ChatMessage.org_id == tenant.org_id,
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )

    if before:
        query = query.where(ChatMessage.created_at < before)

    result = await db.execute(query)
    messages = list(result.scalars().all())
    # Return oldest-first for display
    messages.reverse()

    return [
        ChatMessageResponse(
            id=str(m.id),
            room_id=m.room_id,
            sender_session_id=m.sender_session_id,
            sender_name=m.sender_name,
            content=m.content,
            is_system=m.is_system,
            created_at=m.created_at,
        )
        for m in messages
    ]


@router.post("/messages", status_code=201)
async def create_chat_message(
    body: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    """Persist a chat message (called by Colyseus, fire-and-forget)."""
    msg = ChatMessage(
        room_id=body.room_id,
        sender_session_id=body.sender_session_id,
        sender_name=body.sender_name,
        content=body.content,
        is_system=body.is_system,
        org_id=body.org_id,
    )
    db.add(msg)
    await db.flush()
    return {"status": "created", "id": str(msg.id)}
