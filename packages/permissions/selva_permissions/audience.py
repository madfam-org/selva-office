"""Audience resolution — bridges the swarm's org_id to the tool/skill audience split.

The MADFAM swarm runs under a dedicated Janua org_id (``PLATFORM_ORG_ID``
env var). Tenant swarms run under their own org_id. ``resolve_audience``
is the single choke point that maps org_id → Audience for:

- Workers (at task dispatch)
- Nexus-api (at dispatch endpoint, for 403-on-mismatch)
- Skill registry (for activate audience-check)
- Tool registry (for spec-filter)

This module intentionally avoids importing from ``selva_tools`` or
``selva_skills`` so it stays dep-light; it re-exports string values that
both downstream enums match.
"""

from __future__ import annotations

import enum
import os
from typing import Final

PLATFORM_ORG_ID_ENV: Final[str] = "PLATFORM_ORG_ID"


class Audience(enum.StrEnum):
    """Same enum values as selva_tools.Audience and selva_skills.SkillAudience.

    Kept in selva_permissions so the resolution logic (which depends on
    env config) doesn't force a tools-package import from call sites
    that only need to ask "is this org_id the platform?".
    """

    PLATFORM = "platform"
    TENANT = "tenant"


def get_platform_org_id() -> str | None:
    """Return the configured ``PLATFORM_ORG_ID`` or None if unset.

    Reads the env var on every call (not cached) so container restarts
    and test overrides are respected without a module reimport.
    """
    value = os.environ.get(PLATFORM_ORG_ID_ENV, "")
    return value.strip() or None


def resolve_audience(org_id: str | None) -> Audience:
    """Map a Janua org_id to its swarm audience.

    Rules:
    - If ``PLATFORM_ORG_ID`` is unset → everything is TENANT (the safe
      default; tenant swarms never see platform tools).
    - If ``org_id`` matches ``PLATFORM_ORG_ID`` → PLATFORM.
    - Otherwise → TENANT.

    This is the extension point for multi-admin: swap the comparison
    for a Janua org-metadata lookup (``is_platform: true``) without
    changing any caller.
    """
    platform = get_platform_org_id()
    if org_id and platform and org_id == platform:
        return Audience.PLATFORM
    return Audience.TENANT


def is_platform_audience(org_id: str | None) -> bool:
    """Convenience: ``resolve_audience(org_id) is Audience.PLATFORM``."""
    return resolve_audience(org_id) is Audience.PLATFORM
