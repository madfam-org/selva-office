"""Pydantic models mirroring the nexus-api schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DispatchRequest(BaseModel):
    """Request body for dispatching a swarm task."""

    description: str = Field(..., min_length=1)
    graph_type: str = Field(default="coding")
    assigned_agent_ids: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None


class AgentResponse(BaseModel):
    """Agent data returned from the API."""

    id: str
    name: str
    role: str
    status: str
    level: int
    department_id: str | None = None
    skill_ids: list[str] | None = None
    effective_skills: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    """Task data returned from the API."""

    id: str
    description: str
    graph_type: str
    assigned_agent_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    status: str
    created_at: str
    completed_at: str | None = None
