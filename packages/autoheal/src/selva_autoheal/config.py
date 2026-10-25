"""Configuration, read from the environment. Off by default, fail closed.

Nothing here carries an amount or a grant figure: the caps are deployment
configuration and have no default, so an enabled-but-unconfigured agent
refuses to run (``ConfigError``) instead of guessing a budget.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

PREFIX = "INFRA_AUTOHEAL_"


class ConfigError(ValueError):
    """The agent is enabled but its configuration is incomplete or invalid."""


def _csv(raw: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in raw.split(",") if part.strip())


def _truthy(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AutohealConfig:
    """Everything the intake and the agent need. Build with :meth:`from_env`."""

    enabled: bool = False
    #: Org the agent spends for (grant ``allowed_orgs`` must contain it).
    org_id: str = "madfam"
    #: Providers in preference order (server-set ``provider_allowlist``).
    providers: tuple[str, ...] = ("anthropic-ops", "anthropic")
    model: str = "claude-sonnet-5-5"
    max_tokens: int = 2048
    #: Hard caps, USD. No default: required when enabled.
    incident_cap_usd: float = 0.0
    daily_cap_usd: float = 0.0
    #: Alert names that open an incident. Empty means none qualify.
    alertnames: tuple[str, ...] = ()
    #: Severities that qualify (label ``severity``).
    severities: tuple[str, ...] = ("critical", "warning")
    #: Loop / flap / stop limits.
    max_steps: int = 10
    max_seconds: int = 300
    cooldown_seconds: int = 1800
    max_runs_per_key_per_day: int = 3
    max_incidents_per_day: int = 20
    #: When no Anthropic credential has budget: ``stop`` posts an evidence-only
    #: report marked «sin presupuesto»; ``fallback`` retries the reasoning on
    #: ``fallback_providers`` (paid outside any grant) — owner decision.
    no_budget: Literal["stop", "fallback"] = "stop"
    fallback_providers: tuple[str, ...] = ()
    #: Courier (angelia) delivery. Empty URL or recipient ⇒ not posted (logged).
    courier_url: str = ""
    courier_api_key_env: str = "COURIER_API_KEY"
    courier_tenant: str = ""
    courier_recipient: str = ""
    #: Courier reply threading (needs the angelia ``reply_to`` change).
    courier_threading: bool = False
    #: Enclii read API.
    enclii_api_url: str = ""
    enclii_token_env: str = "ENCLII_AUTOHEAL_TOKEN"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AutohealConfig:
        e = os.environ if env is None else env

        def get(name: str, default: str = "") -> str:
            return str(e.get(PREFIX + name, default)).strip()

        def num(name: str, default: float) -> float:
            raw = get(name)
            if not raw:
                return default
            try:
                return float(raw)
            except ValueError as exc:
                raise ConfigError(f"{PREFIX}{name} is not a number") from exc

        no_budget = get("NO_BUDGET", "stop") or "stop"
        if no_budget not in ("stop", "fallback"):
            raise ConfigError(f"{PREFIX}NO_BUDGET must be stop or fallback")
        cfg = cls(
            enabled=_truthy(get("ENABLED", "false")),
            org_id=get("ORG_ID", "madfam") or "madfam",
            providers=_csv(get("PROVIDERS", "anthropic-ops,anthropic")),
            model=get("MODEL", "claude-sonnet-5-5") or "claude-sonnet-5-5",
            max_tokens=int(num("MAX_TOKENS", 2048)),
            incident_cap_usd=num("INCIDENT_CAP_USD", 0.0),
            daily_cap_usd=num("DAILY_CAP_USD", 0.0),
            alertnames=_csv(get("ALERTNAMES")),
            severities=_csv(get("SEVERITIES", "critical,warning")),
            max_steps=int(num("MAX_STEPS", 10)),
            max_seconds=int(num("MAX_SECONDS", 300)),
            cooldown_seconds=int(num("COOLDOWN_SECONDS", 1800)),
            max_runs_per_key_per_day=int(num("MAX_RUNS_PER_KEY_PER_DAY", 3)),
            max_incidents_per_day=int(num("MAX_INCIDENTS_PER_DAY", 20)),
            no_budget=no_budget,  # type: ignore[arg-type]
            fallback_providers=_csv(get("FALLBACK_PROVIDERS")),
            courier_url=get("COURIER_URL"),
            courier_api_key_env=get("COURIER_API_KEY_ENV", "COURIER_API_KEY") or "COURIER_API_KEY",
            courier_tenant=get("COURIER_TENANT"),
            courier_recipient=get("COURIER_RECIPIENT"),
            courier_threading=_truthy(get("COURIER_THREADING", "false")),
            enclii_api_url=get("ENCLII_API_URL"),
            enclii_token_env=get("ENCLII_TOKEN_ENV", "ENCLII_AUTOHEAL_TOKEN")
            or "ENCLII_AUTOHEAL_TOKEN",
        )
        return cfg

    def validate_for_run(self) -> None:
        """Raise ``ConfigError`` unless the agent may run. Called before any work."""
        if not self.enabled:
            raise ConfigError(f"{PREFIX}ENABLED is not true")
        problems: list[str] = []
        if self.incident_cap_usd <= 0:
            problems.append(f"{PREFIX}INCIDENT_CAP_USD must be > 0")
        if self.daily_cap_usd <= 0:
            problems.append(f"{PREFIX}DAILY_CAP_USD must be > 0")
        if self.daily_cap_usd and self.incident_cap_usd > self.daily_cap_usd:
            problems.append("the incident cap cannot exceed the daily cap")
        if not self.alertnames:
            problems.append(f"{PREFIX}ALERTNAMES is empty (no alert would qualify)")
        if not self.providers:
            problems.append(f"{PREFIX}PROVIDERS is empty")
        if self.no_budget == "fallback" and not self.fallback_providers:
            problems.append(f"{PREFIX}NO_BUDGET=fallback needs {PREFIX}FALLBACK_PROVIDERS")
        if self.max_steps < 1 or self.max_seconds < 10:
            problems.append("max steps / seconds are too small")
        if problems:
            raise ConfigError("; ".join(problems))
