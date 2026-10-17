"""Org-level configuration for inference routing and agent personnel.

Loads ``~/.selva/org-config.yaml`` (or a custom path) and provides
typed models for provider registration, task-type model assignments,
and agent templates.  All API keys are referenced by *env var name*,
never stored as plaintext.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path.home() / ".selva" / "org-config.yaml"


class TaskType(StrEnum):
    """Categories of LLM work — the router picks the best model per type."""

    PLANNING = "planning"
    CODING = "coding"
    FAST_CODING = "fast_coding"
    REVIEW = "review"
    RESEARCH = "research"
    CRM = "crm"
    SUPPORT = "support"
    VISION = "vision"
    EMBEDDING = "embedding"


class ModelAssignment(BaseModel):
    """Maps a task type to a specific provider + model."""

    provider: str
    model: str
    max_tokens: int = 4096
    temperature: float = 0.7


class ProviderConfig(BaseModel):
    """Connection details for an OpenAI-compatible provider."""

    base_url: str
    api_key_env: str
    vision: bool = True
    timeout: float = 120.0


class AgentTemplate(BaseModel):
    """Declarative agent definition for seeding."""

    name: str
    role: str
    level: int = 1
    department_slug: str
    skill_ids: list[str] = []


class ServiceConfig(BaseModel):
    """External service account details for the org."""

    provider: str
    service_type: str  # email, billing, llm, crm, auth, infrastructure, devops
    api_key_env: str  # env var name (never plaintext)
    plan: str = ""  # pro, free, enterprise, pay_as_you_go, self_hosted
    plan_details: str = ""
    payment_method: str = ""  # credit_card, invoice, none
    capacity: dict[str, Any] = {}
    consumption_tracking: bool = False
    status: str = "active"  # active, setup, disabled, pending_key
    notes: str = ""


class OrgOverride(BaseModel):
    """Routing overrides for ONE tenant org (``org_overrides.<org>``).

    Only the named org (and its ``aliases``) is affected; every other
    tenant keeps the global ``model_assignments`` and priority lists
    exactly as they are. Task types not listed here use the global
    assignment. Sensitivity precedence is unchanged: an override
    assignment whose provider is outside the request's sensitivity-allowed
    set is refused like any other assignment.
    """

    #: Other org ids that are the same tenant (e.g. the org's Janua UUID
    #: next to the platform slug ``madfam``).
    aliases: list[str] = []
    model_assignments: dict[TaskType, ModelAssignment] = {}
    #: Replace the global lists for this org only. Must still include the
    #: global provider so the org can fall back to it.
    cloud_priority: list[str] | None = None
    cheapest_priority: list[str] | None = None
    notes: str = ""


class OrgConfig(BaseModel):
    """Top-level org configuration loaded from YAML."""

    providers: dict[str, ProviderConfig] = {}
    model_assignments: dict[TaskType, ModelAssignment] = {}
    cloud_priority: list[str] | None = None
    cheapest_priority: list[str] | None = None
    agents: list[AgentTemplate] = []
    services: dict[str, ServiceConfig] = {}
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    org_overrides: dict[str, OrgOverride] = {}

    def override_for(self, org_id: str | None) -> OrgOverride | None:
        """Return the ``org_overrides`` entry for ``org_id`` (key or alias)."""
        if not org_id or not self.org_overrides:
            return None
        direct = self.org_overrides.get(org_id)
        if direct is not None:
            return direct
        for override in self.org_overrides.values():
            if org_id in override.aliases:
                return override
        return None


def _resolve_api_key(env_var_name: str) -> str | None:
    """Resolve an API key from an environment variable name."""
    return os.environ.get(env_var_name)


def _convert_assignments(section: dict[str, Any]) -> None:
    """Convert string task-type keys of ``section["model_assignments"]`` in place."""
    if "model_assignments" in section and isinstance(section["model_assignments"], dict):
        converted: dict[TaskType, Any] = {}
        for key, value in section["model_assignments"].items():
            try:
                converted[TaskType(key)] = value
            except ValueError:
                logger.warning("Unknown task type in org config: %s", key)
        section["model_assignments"] = converted


def _parse_yaml(raw: dict[str, Any]) -> OrgConfig:
    """Parse a raw YAML dict into an OrgConfig, handling TaskType key conversion."""
    _convert_assignments(raw)
    # Per-org overrides are validated one by one and an invalid entry is
    # DROPPED (logged at ERROR): a typo in one tenant's override must never
    # take down the global routing every other tenant depends on, and a
    # dropped override means that org simply gets the global routing.
    overrides = raw.pop("org_overrides", None)
    parsed: dict[str, OrgOverride] = {}
    if isinstance(overrides, dict):
        for org, section in overrides.items():
            if not isinstance(section, dict):
                logger.error("org_overrides.%s is not a mapping — ignored", org)
                continue
            _convert_assignments(section)
            try:
                parsed[str(org)] = OrgOverride(**section)
            except Exception as exc:
                logger.error("org_overrides.%s is invalid and was NOT applied: %s", org, exc)
    elif overrides is not None:
        logger.error("org_overrides must be a mapping — ignored")
    config = OrgConfig(**raw)
    config.org_overrides = parsed
    return config


@lru_cache(maxsize=1)
def load_org_config(path: Path | None = None) -> OrgConfig:
    """Load org config from YAML, returning defaults if the file is missing.

    The result is cached per process via ``@lru_cache``.
    """
    config_path = path or _DEFAULT_CONFIG_PATH

    if not config_path.exists():
        logger.debug("No org config at %s — using defaults", config_path)
        return OrgConfig()

    try:
        import yaml

        raw = yaml.safe_load(config_path.read_text()) or {}
        config = _parse_yaml(raw)
        logger.info(
            "Loaded org config from %s (%d providers, %d assignments)",
            config_path,
            len(config.providers),
            len(config.model_assignments),
        )
        return config
    except ImportError:
        logger.warning("PyYAML not installed — cannot load org config; using defaults")
        return OrgConfig()
    except Exception:
        logger.warning(
            "Failed to parse org config at %s — using defaults", config_path, exc_info=True
        )
        return OrgConfig()
