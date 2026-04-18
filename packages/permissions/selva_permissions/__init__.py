"""AutoSwarm Permissions -- HITL permission system with action classification."""

from .classifier import ActionClassifier
from .context_rules import (
    DEFAULT_CONTEXT_RULES,
    ContextRule,
    PermissionContext,
    RiskScoreRule,
    RoleMatrixRule,
    TimeOfDayRule,
    TrustLevelRule,
)
from .engine import PermissionEngine
from .matrix import DEFAULT_PERMISSION_MATRIX
from .role_matrices import ROLE_PERMISSION_MATRICES

__all__ = [
    "ActionClassifier",
    "ContextRule",
    "DEFAULT_CONTEXT_RULES",
    "DEFAULT_PERMISSION_MATRIX",
    "PermissionContext",
    "PermissionEngine",
    "RiskScoreRule",
    "ROLE_PERMISSION_MATRICES",
    "RoleMatrixRule",
    "TimeOfDayRule",
    "TrustLevelRule",
]
