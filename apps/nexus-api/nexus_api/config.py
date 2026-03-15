"""Application configuration via environment variables and .env files."""

from __future__ import annotations

import warnings
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Resolve project root so env_file works regardless of CWD.
# config.py -> nexus_api -> nexus-api -> apps -> project root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Central configuration for the Nexus API.

    All values are read from environment variables (case-insensitive) and
    can be overridden via a ``.env`` file at the project root.
    """

    # -- Infrastructure -------------------------------------------------------
    database_url: str = "postgresql+asyncpg://autoswarm:autoswarm@localhost:5432/autoswarm"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 1800  # 30 minutes
    db_pool_timeout: int = 30
    redis_url: str = "redis://localhost:6379"

    # -- Auth (Janua OIDC) ----------------------------------------------------
    janua_issuer_url: str = "https://auth.madfam.io"
    janua_client_id: str = "autoswarm-office"
    janua_client_secret: str = ""

    # -- Billing (Dhanam) -----------------------------------------------------
    dhanam_api_url: str = "https://api.dhan.am"
    dhanam_webhook_secret: str = ""

    # -- Gateway (GitHub webhooks) ---------------------------------------------
    github_webhook_secret: str = ""

    # -- Enclii (deployment webhooks) ------------------------------------------
    enclii_webhook_secret: str = ""

    # -- AI Inference ---------------------------------------------------------
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openrouter_api_key: str | None = None
    together_api_key: str | None = None
    fireworks_api_key: str | None = None
    deepinfra_api_key: str | None = None
    siliconflow_api_key: str | None = None
    moonshot_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    org_config_path: str = "~/.autoswarm/org-config.yaml"

    # -- Phyne-CRM ------------------------------------------------------------
    phyne_crm_url: str | None = None

    # -- Colyseus -------------------------------------------------------------
    colyseus_secret: str = "change-me-in-production"

    # -- Server ---------------------------------------------------------------
    environment: str = "production"
    port: int = 4300
    cors_origins: list[str] = [
        "http://localhost:4301",
        "http://localhost:4302",
    ]

    # -- Security -------------------------------------------------------------
    dev_auth_bypass: bool = False
    rate_limit_per_minute: int = 60
    dispatch_rate_limit: int = 10
    dispatch_rate_window: int = 60
    csp_extra_sources: str = ""
    log_format: str = "json"

    model_config = {
        "env_file": (str(_PROJECT_ROOT / ".env"), ".env"),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def _validate_config(self) -> Settings:
        """Validate configuration values and warn about insecure defaults."""
        if self.dev_auth_bypass and self.environment != "development":
            warnings.warn(
                "DEV_AUTH_BYPASS is enabled in a non-development environment! "
                "This is a security risk.",
                stacklevel=2,
            )

        if not self.database_url.startswith(("postgresql", "sqlite")):
            raise ValueError(
                f"DATABASE_URL must start with 'postgresql' or 'sqlite', "
                f"got: {self.database_url[:20]}..."
            )

        if not self.redis_url.startswith("redis"):
            raise ValueError(
                f"REDIS_URL must start with 'redis://' or 'rediss://', "
                f"got: {self.redis_url[:20]}..."
            )

        if (
            self.colyseus_secret == "change-me-in-production"
            and self.environment != "development"
        ):
            warnings.warn(
                "COLYSEUS_SECRET is set to default value in non-development environment!",
                stacklevel=2,
            )

        return self


def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
