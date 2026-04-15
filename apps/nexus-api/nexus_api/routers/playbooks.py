"""Playbook CRUD API — manage bounded autonomous execution playbooks.

Playbooks define pre-approved action sequences that agents can execute
without HITL approval, within strict token + dollar boundaries.
See docs/SWARM_MANIFESTO.md Axiom IV.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/playbooks", tags=["playbooks"])


# ── Schemas ──────────────────────────────────────────────────────────

class PlaybookCreate(BaseModel):
    name: str = Field(..., max_length=100)
    trigger_event: str = Field(..., max_length=200, description="Event key (e.g., 'crm:hot_lead')")
    allowed_actions: list[str] = Field(..., description="ActionCategory values allowed without HITL")
    token_budget: int = Field(50, ge=1, le=10000, description="Max compute tokens per execution")
    financial_cap_cents: int = Field(0, ge=0, le=100000, description="Max USD cents exposure per execution")
    require_approval: bool = Field(False, description="If True, playbook still requires HITL")
    enabled: bool = Field(True)


class PlaybookUpdate(BaseModel):
    name: str | None = None
    allowed_actions: list[str] | None = None
    token_budget: int | None = None
    financial_cap_cents: int | None = None
    require_approval: bool | None = None
    enabled: bool | None = None


class PlaybookResponse(BaseModel):
    id: str
    name: str
    trigger_event: str
    allowed_actions: list[str]
    token_budget: int
    financial_cap_cents: int
    require_approval: bool
    enabled: bool
    org_id: str
    created_at: str

    model_config = {"from_attributes": True}


# ── In-Memory Store ──────────────────────────────────────────────────
# Using a simple in-memory dict until the Alembic migration for the
# Playbook SQLAlchemy model is created. This allows the API to work
# immediately without a database migration.

_playbooks: dict[str, dict[str, Any]] = {}

# Seed default playbooks on module load
_SEED_PLAYBOOKS = [
    {
        "name": "Lead Response",
        "trigger_event": "crm:hot_lead",
        "allowed_actions": ["api_call", "email_send", "crm_update", "marketing_send"],
        "token_budget": 50,
        "financial_cap_cents": 0,
        "require_approval": False,
        "enabled": True,
    },
    {
        "name": "Content Publish",
        "trigger_event": "content:scheduled_post",
        "allowed_actions": ["api_call"],
        "token_budget": 30,
        "financial_cap_cents": 0,
        "require_approval": False,
        "enabled": True,
    },
    {
        "name": "Trial Retention",
        "trigger_event": "billing:trial_expiring",
        "allowed_actions": ["api_call", "email_send", "marketing_send"],
        "token_budget": 40,
        "financial_cap_cents": 0,
        "require_approval": False,
        "enabled": True,
    },
    # ═══ INFRASTRUCTURE PLAYBOOKS ═══
    {
        "name": "Auto-Restart on Pod Crash",
        "trigger_event": "infra:pod_crash",
        "allowed_actions": ["infra_monitor", "deploy"],
        "token_budget": 20,
        "financial_cap_cents": 0,
        "require_approval": False,
        "enabled": True,
    },
    {
        "name": "Automated Health Analysis",
        "trigger_event": "infra:health_degraded",
        "allowed_actions": ["infra_monitor", "api_call"],
        "token_budget": 10,
        "financial_cap_cents": 0,
        "require_approval": False,
        "enabled": True,
    },
    {
        "name": "Database Migration Runner",
        "trigger_event": "infra:migration_pending",
        "allowed_actions": ["infrastructure_exec", "database_migration", "infra_monitor"],
        "token_budget": 30,
        "financial_cap_cents": 0,
        "require_approval": True,
        "enabled": True,
    },
]

for _seed in _SEED_PLAYBOOKS:
    _id = str(uuid.uuid4())
    _playbooks[_id] = {
        "id": _id,
        **_seed,
        "org_id": "madfam-default",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Endpoints ────────────────────────────────────────────────────────

@router.get("", response_model=list[PlaybookResponse])
async def list_playbooks():
    """List all playbooks."""
    return list(_playbooks.values())


@router.post("", response_model=PlaybookResponse, status_code=201)
async def create_playbook(body: PlaybookCreate):
    """Create a new playbook."""
    playbook_id = str(uuid.uuid4())
    playbook = {
        "id": playbook_id,
        **body.model_dump(),
        "org_id": "madfam-default",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _playbooks[playbook_id] = playbook
    logger.info("Playbook created: %s (%s)", body.name, playbook_id)
    return playbook


@router.get("/match")
async def match_playbook(event: str):
    """Find a matching enabled playbook for a trigger event.

    Used by HeartbeatService and webhook handlers to resolve which
    playbook (if any) should gate an auto-dispatched task.
    """
    for pb in _playbooks.values():
        if pb["trigger_event"] == event and pb["enabled"] and not pb["require_approval"]:
            return pb
    raise HTTPException(status_code=404, detail=f"No matching playbook for event: {event}")


@router.get("/{playbook_id}", response_model=PlaybookResponse)
async def get_playbook(playbook_id: str):
    """Get a playbook by ID."""
    if playbook_id not in _playbooks:
        raise HTTPException(status_code=404, detail="Playbook not found")
    return _playbooks[playbook_id]


@router.patch("/{playbook_id}", response_model=PlaybookResponse)
async def update_playbook(playbook_id: str, body: PlaybookUpdate):
    """Update a playbook."""
    if playbook_id not in _playbooks:
        raise HTTPException(status_code=404, detail="Playbook not found")

    updates = body.model_dump(exclude_unset=True)
    _playbooks[playbook_id].update(updates)
    logger.info("Playbook updated: %s", playbook_id)
    return _playbooks[playbook_id]


@router.delete("/{playbook_id}", status_code=204)
async def delete_playbook(playbook_id: str):
    """Delete a playbook."""
    if playbook_id not in _playbooks:
        raise HTTPException(status_code=404, detail="Playbook not found")
    del _playbooks[playbook_id]
    logger.info("Playbook deleted: %s", playbook_id)
