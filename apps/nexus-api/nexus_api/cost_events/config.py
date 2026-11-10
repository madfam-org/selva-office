"""Configuration of the cost-events emitter, read from the environment.

Plain environment variables (not ``Settings``) so the emitter stays dormant
and self-contained: nothing here is read unless the command or the sweep runs.

==========================================  =====================================================
Variable                                    Meaning
==========================================  =====================================================
``SELVA_COST_EVENTS_EMIT_ENABLED``          ``true`` sends to Dhanam. Anything else: off (the dry
                                            run still works).
``SELVA_DHANAM_COST_EVENTS_CLIENT_ID``      Janua ``client_credentials`` pair of the enclii platform
``SELVA_DHANAM_COST_EVENTS_CLIENT_SECRET``  ``selva-dhanam-cost-events`` (audience ``dhanam-api``).
``JANUA_ISSUER_URL``                        Janua issuer; the token endpoint is
                                            ``{issuer}/api/v1/oauth/token`` (https only).
``DHANAM_API_URL``                          Dhanam API origin (``/v1`` is added when absent).
``SELVA_COST_EVENTS_LOOKBACK_DAYS``         Closed civil days rebuilt on every sweep (default 7,
                                            1–62): late rows and grant edits are corrected.
``SELVA_COST_EVENTS_START_DATE``            Optional ``YYYY-MM-DD``: no day before it is ever built.
``SELVA_COST_EVENTS_CONTRACT_FEATURES``     Comma list of contract additions Dhanam accepts:
                                            ``attribution_product`` (contract v1.1) and
                                            ``funding_memo`` (proposed, see docs/COST_EVENTS.md).
                                            Default empty = contract v1.0.
``SELVA_COST_EVENTS_LOCAL_PROVIDERS``       Providers that run on MADFAM's own compute (default
                                            ``ollama``): their tokens have no token cost.
``SELVA_COST_EVENTS_PRODUCT_BY_CALLER``     JSON ``{caller: product_slug}``: inference a
                                            client-facing product asked for (``caller`` is the
                                            calling service's identity on the ledger row).
``SELVA_COST_EVENTS_ENGAGEMENT_BY_ORG``     JSON ``{org_id: engagement_slug}``: a Selva tenant
                                            whose usage belongs to one engagement (RFC 0050 D6).
``SELVA_COST_EVENTS_PLATFORM_ORGS``         Extra org ids that mean MADFAM itself (always included:
                                            ``PLATFORM_ORG_ID``, ``madfam``, ``platform``,
                                            ``default``).
==========================================  =====================================================

A malformed value is a configuration error, never a silent default: the
command exits non-zero and names the variable (never its value).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urlsplit

ENV_ENABLED = "SELVA_COST_EVENTS_EMIT_ENABLED"
ENV_CLIENT_ID = "SELVA_DHANAM_COST_EVENTS_CLIENT_ID"
ENV_CLIENT_SECRET = "SELVA_DHANAM_COST_EVENTS_CLIENT_SECRET"  # noqa: S105 - env var name
ENV_JANUA_ISSUER = "JANUA_ISSUER_URL"
ENV_DHANAM_URL = "DHANAM_API_URL"
ENV_LOOKBACK = "SELVA_COST_EVENTS_LOOKBACK_DAYS"
ENV_START_DATE = "SELVA_COST_EVENTS_START_DATE"
ENV_FEATURES = "SELVA_COST_EVENTS_CONTRACT_FEATURES"
ENV_LOCAL_PROVIDERS = "SELVA_COST_EVENTS_LOCAL_PROVIDERS"
ENV_PRODUCT_BY_CALLER = "SELVA_COST_EVENTS_PRODUCT_BY_CALLER"
ENV_ENGAGEMENT_BY_ORG = "SELVA_COST_EVENTS_ENGAGEMENT_BY_ORG"
ENV_PLATFORM_ORGS = "SELVA_COST_EVENTS_PLATFORM_ORGS"
ENV_PLATFORM_ORG_ID = "PLATFORM_ORG_ID"

#: ONE colon: Janua registers only ``namespace:action`` scopes.
SCOPE = "dhanam-cost-events:write"
JANUA_TOKEN_PATH = "/api/v1/oauth/token"

FEATURE_PRODUCT = "attribution_product"
FEATURE_FUNDING_MEMO = "funding_memo"
KNOWN_FEATURES = frozenset({FEATURE_PRODUCT, FEATURE_FUNDING_MEMO})

DEFAULT_LOOKBACK_DAYS = 7
MAX_LOOKBACK_DAYS = 62
#: Org ids that always mean MADFAM's own tenant (the inference proxy stores
#: usage without an org as ``platform``; worker debits default to ``default``).
BUILTIN_PLATFORM_ORGS = frozenset({"madfam", "platform", "default"})

#: Dhanam's ``attribution.product`` and ``eng:<slug>`` grammars.
SLUG = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class CostEventsConfigError(ValueError):
    """A variable is malformed. The message names the variable, never its value."""


@dataclass(frozen=True)
class CostEventsConfig:
    enabled: bool = False
    client_id: str = ""
    client_secret: str = field(default="", repr=False)
    token_url: str = ""
    events_url: str = ""
    lookback_days: int = DEFAULT_LOOKBACK_DAYS
    start_date: date | None = None
    features: frozenset[str] = frozenset()
    local_providers: frozenset[str] = frozenset({"ollama"})
    product_by_caller: dict[str, str] = field(default_factory=dict)
    engagement_by_org: dict[str, str] = field(default_factory=dict)
    platform_orgs: frozenset[str] = BUILTIN_PLATFORM_ORGS

    def missing_for_send(self) -> list[str]:
        """Variables a real send still needs (names only)."""
        missing = []
        if not self.client_id:
            missing.append(ENV_CLIENT_ID)
        if not self.client_secret:
            missing.append(ENV_CLIENT_SECRET)
        if not self.token_url:
            missing.append(ENV_JANUA_ISSUER)
        if not self.events_url:
            missing.append(ENV_DHANAM_URL)
        return missing

    def has(self, feature: str) -> bool:
        return feature in self.features


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("true", "1", "yes")


def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _slug_map(env: dict[str, str], name: str) -> dict[str, str]:
    raw = (env.get(name) or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise CostEventsConfigError(f"{name} must be a JSON object") from None
    if not isinstance(data, dict):
        raise CostEventsConfigError(f"{name} must be a JSON object")
    out: dict[str, str] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise CostEventsConfigError(f"{name} keys must be non-empty strings")
        if not isinstance(value, str) or not SLUG.match(value):
            raise CostEventsConfigError(f"{name} values must be lowercase slugs")
        out[key.strip()] = value
    return out


def _https_url(env: dict[str, str], name: str) -> str:
    """``scheme://host[:port][/path]`` without a trailing slash, or "" when unset."""
    raw = (env.get(name) or "").strip().rstrip("/")
    if not raw:
        return ""
    parts = urlsplit(raw)
    secure = parts.scheme == "https" or (
        parts.scheme == "http" and parts.hostname in _LOOPBACK_HOSTS
    )
    if not parts.hostname or not secure:
        raise CostEventsConfigError(f"{name} must be an https URL")
    return raw


def events_endpoint(dhanam_url: str) -> str:
    """``POST`` target: ``DHANAM_API_URL`` is a bare origin in Selva's config."""
    if not dhanam_url:
        return ""
    base = dhanam_url if dhanam_url.endswith("/v1") else f"{dhanam_url}/v1"
    return f"{base}/cost-events"


def load_config(env: dict[str, str] | None = None) -> CostEventsConfig:
    env = dict(os.environ) if env is None else env

    raw_lookback = (env.get(ENV_LOOKBACK) or "").strip()
    lookback = DEFAULT_LOOKBACK_DAYS
    if raw_lookback:
        if not raw_lookback.isdigit() or not 1 <= int(raw_lookback) <= MAX_LOOKBACK_DAYS:
            raise CostEventsConfigError(f"{ENV_LOOKBACK} must be 1–{MAX_LOOKBACK_DAYS}")
        lookback = int(raw_lookback)

    start: date | None = None
    raw_start = (env.get(ENV_START_DATE) or "").strip()
    if raw_start:
        try:
            start = date.fromisoformat(raw_start)
        except ValueError:
            raise CostEventsConfigError(f"{ENV_START_DATE} must be YYYY-MM-DD") from None

    features = frozenset(f.lower() for f in _csv(env.get(ENV_FEATURES)))
    unknown = features - KNOWN_FEATURES
    if unknown:
        raise CostEventsConfigError(
            f"{ENV_FEATURES} accepts only {', '.join(sorted(KNOWN_FEATURES))}"
        )

    local = frozenset(p.lower() for p in _csv(env.get(ENV_LOCAL_PROVIDERS, "ollama")))

    platform_org = (env.get(ENV_PLATFORM_ORG_ID) or "").strip()
    platform_orgs = set(BUILTIN_PLATFORM_ORGS) | set(_csv(env.get(ENV_PLATFORM_ORGS)))
    if platform_org:
        platform_orgs.add(platform_org)

    issuer = _https_url(env, ENV_JANUA_ISSUER)
    return CostEventsConfig(
        enabled=_flag(env.get(ENV_ENABLED)),
        client_id=(env.get(ENV_CLIENT_ID) or "").strip(),
        client_secret=(env.get(ENV_CLIENT_SECRET) or "").strip(),
        token_url=f"{issuer}{JANUA_TOKEN_PATH}" if issuer else "",
        events_url=events_endpoint(_https_url(env, ENV_DHANAM_URL)),
        lookback_days=lookback,
        start_date=start,
        features=features,
        local_providers=local,
        product_by_caller=_slug_map(env, ENV_PRODUCT_BY_CALLER),
        engagement_by_org=_slug_map(env, ENV_ENGAGEMENT_BY_ORG),
        platform_orgs=frozenset(platform_orgs),
    )
