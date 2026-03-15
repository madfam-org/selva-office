"""Intelligence configuration endpoint — control plane for MADFAM inference."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from madfam_inference.org_config import OrgConfig, TaskType, load_org_config

from ..auth import get_current_user
from ..config import get_settings

router = APIRouter(tags=["intelligence"], dependencies=[Depends(get_current_user)])


class ModelAssignmentResponse(BaseModel):
    """Model assignment without sensitive fields."""

    provider: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7


class ProviderSummary(BaseModel):
    """Provider info with api_key_env redacted."""

    base_url: str
    vision: bool = True
    timeout: float = 120.0


class OrgConfigResponse(BaseModel):
    """Org-level inference config — safe for API consumers.

    API keys and agent templates are intentionally excluded.
    """

    providers: dict[str, ProviderSummary] = {}
    model_assignments: dict[str, ModelAssignmentResponse] = {}
    cloud_priority: list[str] | None = None
    cheapest_priority: list[str] | None = None
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"


def _safe_config(cfg: OrgConfig) -> OrgConfigResponse:
    """Strip sensitive fields from OrgConfig for API response."""
    providers: dict[str, ProviderSummary] = {}
    for name, p in cfg.providers.items():
        providers[name] = ProviderSummary(
            base_url=p.base_url,
            vision=p.vision,
            timeout=p.timeout,
        )

    assignments: dict[str, ModelAssignmentResponse] = {}
    for task_type, ma in cfg.model_assignments.items():
        key = task_type.value if isinstance(task_type, TaskType) else str(task_type)
        assignments[key] = ModelAssignmentResponse(
            provider=ma.provider,
            model=ma.model,
            max_tokens=ma.max_tokens,
            temperature=ma.temperature,
        )

    return OrgConfigResponse(
        providers=providers,
        model_assignments=assignments,
        cloud_priority=cfg.cloud_priority,
        cheapest_priority=cfg.cheapest_priority,
        embedding_provider=cfg.embedding_provider,
        embedding_model=cfg.embedding_model,
    )


@router.get("/config", response_model=OrgConfigResponse)
async def get_intelligence_config() -> OrgConfigResponse:
    """Return org-level inference config (providers, model assignments, priorities).

    API keys are NEVER included in the response.
    """
    settings = get_settings()
    cfg = load_org_config(Path(settings.org_config_path).expanduser())
    return _safe_config(cfg)
