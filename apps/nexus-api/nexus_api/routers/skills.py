"""Skills listing, community-skills toggle, and progressive disclosure endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from autoswarm_skills import SkillTier, get_skill_registry
from autoswarm_skills.skill_md import SkillMDRegistry  # Gap 4

from ..auth import get_current_user

router = APIRouter(tags=["skills"], dependencies=[Depends(get_current_user)])

# Gap 4: singleton SkillMDRegistry, loaded at import time
_md_registry = SkillMDRegistry()
_md_registry.load_md_skills()


class SkillResponse(BaseModel):
    """Public representation of a skill."""

    name: str
    description: str
    tier: str
    allowed_tools: list[str]


class SkillCompactResponse(BaseModel):
    """Level-0: compact skill metadata (~3k tokens for full catalogue)."""
    name: str
    description: str
    category: str


# ---------------------------------------------------------------------------
# Existing endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[SkillResponse])
async def list_skills(tier: str | None = None) -> list[SkillResponse]:
    """Return all discovered skills, optionally filtered by tier."""
    registry = get_skill_registry()
    tier_filter = SkillTier(tier) if tier else None
    return [
        SkillResponse(
            name=m.name,
            description=m.description,
            tier=m.tier.value,
            allowed_tools=m.allowed_tools,
        )
        for m in registry.list_skills(tier=tier_filter)
    ]


@router.post("/community/enable", status_code=status.HTTP_204_NO_CONTENT)
async def enable_community() -> None:
    """Enable community skills at runtime."""
    get_skill_registry().enable_community_skills()


@router.post("/community/disable", status_code=status.HTTP_204_NO_CONTENT)
async def disable_community() -> None:
    """Disable community skills at runtime."""
    get_skill_registry().disable_community_skills()


@router.get("/community/status")
async def community_status() -> dict[str, bool]:
    """Return whether community skills are currently enabled."""
    return {"enabled": get_skill_registry().community_enabled}


# ---------------------------------------------------------------------------
# Gap 4: Progressive disclosure endpoints (3-level, SKILL.md format)
# ---------------------------------------------------------------------------

@router.get("/compact", response_model=list[SkillCompactResponse])
async def list_skills_compact() -> list[SkillCompactResponse]:
    """
    Level 0: Compact skill index.

    Returns [{name, description, category}] for all SKILL.md skills.
    Approximately 3,000 tokens for a 50-skill catalogue.
    Intended for LLM context injection before a phase loads full skill content.
    """
    return [SkillCompactResponse(**s) for s in _md_registry.list_skills_compact()]


@router.get("/md/{skill_name}")
async def get_skill_full(skill_name: str) -> dict:
    """
    Level 1: Full SKILL.md content for a named skill.

    Returns the complete SKILL.md text. Use this when the agent decides
    it needs full instructions for a specific skill.
    """
    content = _md_registry.get_skill_full(skill_name)
    if content is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
    return {"name": skill_name, "content": content}


@router.get("/md/{skill_name}/refs/{ref_path:path}")
async def get_skill_reference(skill_name: str, ref_path: str) -> dict:
    """
    Level 2: Specific reference file within a skill directory.

    Useful for loading supplementary docs, API references, or example code
    without loading the entire skill context.
    """
    content = _md_registry.get_skill_reference(skill_name, ref_path)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Reference '{ref_path}' not found in skill '{skill_name}'"
        )
    return {"skill": skill_name, "ref_path": ref_path, "content": content}


# ---------------------------------------------------------------------------
# Refiner metrics endpoint
# ---------------------------------------------------------------------------

@router.get("/refiner/metrics")
async def refiner_metrics(
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Return accumulated metrics from the most recent SkillRefiner run.

    Useful for monitoring the health of the skill self-improvement loop.
    """
    from autoswarm_skills.refiner import SkillRefiner

    refiner = SkillRefiner()
    metrics = refiner.get_metrics()
    return {
        "skills_checked": metrics.skills_checked,
        "skills_refined": metrics.skills_refined,
        "skills_failed": metrics.skills_failed,
        "total_iterations": metrics.total_iterations,
        "avg_refinement_ms": metrics.avg_refinement_ms,
    }
