"""Core types for AgentSkills-standard skill definitions."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class SkillTier(StrEnum):
    """Classification tier for skills."""

    CORE = "core"
    COMMUNITY = "community"


class SkillAudience(StrEnum):
    """Swarm audience a skill is intended for.

    Mirrors ``selva_tools.Audience`` by value so the nexus-api dispatch
    gate can compare/cast between the two enums. Skills default to
    ``TENANT`` — platform-only runbooks (cluster-triage, dns-migration,
    incident-triage, staging-refresh, tenant-onboarding) must declare
    ``audience: platform`` in their SKILL.md frontmatter.
    """

    PLATFORM = "platform"
    TENANT = "tenant"


class SkillMetadata(BaseModel):
    """Lightweight metadata from SKILL.md YAML frontmatter (~100 tokens)."""

    name: str = Field(..., max_length=64, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    description: str = Field(..., max_length=1024)
    tier: SkillTier = SkillTier.CORE
    audience: SkillAudience = SkillAudience.TENANT
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class SkillDefinition(BaseModel):
    """Full skill: metadata + markdown body (loaded on activation)."""

    meta: SkillMetadata
    instructions: str
    skill_dir: Path

    model_config = {"arbitrary_types_allowed": True}
