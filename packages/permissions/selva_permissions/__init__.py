"""Selva Permissions -- HITL permission system with action classification."""

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
from .modes import PermissionMode, apply_mode, resolve_mode
from .role_matrices import ROLE_PERMISSION_MATRICES
from .types import ActionCategory, PermissionLevel, PermissionResult

__all__ = [
    "ActionCategory",
    "ActionClassifier",
    "ContextRule",
    "DEFAULT_CONTEXT_RULES",
    "DEFAULT_PERMISSION_MATRIX",
    "PermissionContext",
    "PermissionEngine",
    "PermissionLevel",
    "PermissionMode",
    "PermissionResult",
    "ROLE_PERMISSION_MATRICES",
    "RiskScoreRule",
    "RoleMatrixRule",
    "TimeOfDayRule",
    "TrustLevelRule",
    "apply_mode",
    "resolve_mode",
]
