"""Worker process configuration."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve project root so env_file works regardless of CWD.
# config.py -> autoswarm_workers -> workers -> apps -> project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Configuration for LangGraph execution workers.

    Values are read from environment variables and can be overridden with
    a ``.env`` file in the worker root.
    """

    # -- Infrastructure -------------------------------------------------------
    redis_url: str = "redis://localhost:6379"
    nexus_api_url: str = "http://localhost:4300"
    database_url: str | None = None

    # -- Phyne-CRM ------------------------------------------------------------
    phyne_crm_url: str | None = None
    phyne_crm_token: str | None = None

    # -- Search ---------------------------------------------------------------
    search_api_key: str | None = None
    search_provider: str = "tavily"
    repo_base_path: str = "/tmp/autoswarm-repos"

    # -- GitHub / Deployment ---------------------------------------------------
    github_token: str | None = None
    enclii_deploy_token: str | None = None

    # -- AI Inference ---------------------------------------------------------
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    together_api_key: str | None = None
    fireworks_api_key: str | None = None
    deepinfra_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "claude-sonnet-4-20250514"
    inference_sensitivity: str = "internal"

    model_config = {
        "env_file": (str(_PROJECT_ROOT / ".env"), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
