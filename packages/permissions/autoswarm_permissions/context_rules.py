"""Context-aware permission rules that can escalate decisions.

Rules can escalate ALLOW -> ASK or ASK -> DENY but never relax permissions.
"""

from __future__ import annotations

import abc
from datetime import datetime, timezone

from pydantic import BaseModel

from .types import ActionCategory, PermissionLevel


class PermissionContext(BaseModel):
    """Contextual information passed to context rules."""

    time_utc: datetime | None = None
    agent_level: int | None = None
    risk_score: float | None = None
    agent_role: str | None = None


class ContextRule(abc.ABC):
    """Abstract base for context-aware permission rules."""

    @abc.abstractmethod
    def evaluate(
        self,
        category: ActionCategory,
        level: PermissionLevel,
        context: PermissionContext,
    ) -> PermissionLevel | None:
        """Return a new level to escalate to, or ``None`` to leave unchanged."""


# Destructive actions that are subject to time/trust restrictions.
_DESTRUCTIVE_ACTIONS = frozenset({
    ActionCategory.GIT_PUSH,
    ActionCategory.DEPLOY,
    ActionCategory.EMAIL_SEND,
})


class TimeOfDayRule(ContextRule):
    """Block destructive actions outside business hours (06:00-22:00 UTC)."""

    def __init__(self, start_hour: int = 6, end_hour: int = 22) -> None:
        self.start_hour = start_hour
        self.end_hour = end_hour

    def evaluate(
        self,
        category: ActionCategory,
        level: PermissionLevel,
        context: PermissionContext,
    ) -> PermissionLevel | None:
        if context.time_utc is None:
            return None
        hour = context.time_utc.hour
        if category in _DESTRUCTIVE_ACTIONS and not (self.start_hour <= hour < self.end_hour):
            if level == PermissionLevel.ALLOW:
                return PermissionLevel.ASK
            if level == PermissionLevel.ASK:
                return PermissionLevel.DENY
        return None


class TrustLevelRule(ContextRule):
    """Escalate ALLOW to ASK for low-trust agents (level < 3) on destructive actions."""

    def __init__(self, min_level: int = 3) -> None:
        self.min_level = min_level

    def evaluate(
        self,
        category: ActionCategory,
        level: PermissionLevel,
        context: PermissionContext,
    ) -> PermissionLevel | None:
        if context.agent_level is None:
            return None
        if context.agent_level < self.min_level and category in _DESTRUCTIVE_ACTIONS:
            if level == PermissionLevel.ALLOW:
                return PermissionLevel.ASK
        return None


class RiskScoreRule(ContextRule):
    """Force ASK when risk score exceeds threshold."""

    def __init__(self, threshold: float = 0.8) -> None:
        self.threshold = threshold

    def evaluate(
        self,
        category: ActionCategory,
        level: PermissionLevel,
        context: PermissionContext,
    ) -> PermissionLevel | None:
        if context.risk_score is None:
            return None
        if context.risk_score > self.threshold and level == PermissionLevel.ALLOW:
            return PermissionLevel.ASK
        return None


class RoleMatrixRule(ContextRule):
    """Apply per-role permission overrides from a role matrix."""

    def __init__(
        self,
        role_matrices: dict[str, dict[ActionCategory, PermissionLevel]],
    ) -> None:
        self._role_matrices = role_matrices

    def evaluate(
        self,
        category: ActionCategory,
        level: PermissionLevel,
        context: PermissionContext,
    ) -> PermissionLevel | None:
        if context.agent_role is None:
            return None
        role_matrix = self._role_matrices.get(context.agent_role)
        if role_matrix is None:
            return None
        role_level = role_matrix.get(category)
        if role_level is None:
            return None
        # Only escalate, never relax.
        if _severity(role_level) > _severity(level):
            return role_level
        return None


def _severity(level: PermissionLevel) -> int:
    """Return numeric severity: ALLOW=0, ASK=1, DENY=2."""
    return {
        PermissionLevel.ALLOW: 0,
        PermissionLevel.ASK: 1,
        PermissionLevel.DENY: 2,
    }[level]


# Default rules applied when context is provided.
DEFAULT_CONTEXT_RULES: list[ContextRule] = [
    TimeOfDayRule(),
    TrustLevelRule(),
    RiskScoreRule(),
]
