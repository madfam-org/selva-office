"""Selva Permissions -- HITL permission system with action classification."""

from .classifier import ActionClassifier
from .confidence import (
    INITIAL_BUCKET_STATE,
    BucketState,
    ConfidenceTier,
    DecisionOutcome,
    apply_decision,
    current_tier,
)
from .context_rules import (
    DEFAULT_CONTEXT_RULES,
    ContextRule,
    PermissionContext,
    RiskScoreRule,
    RoleMatrixRule,
    TimeOfDayRule,
    TrustLevelRule,
)
from .context_signature import (
    SIGNATURE_VERSION,
    compute_bucket_key,
    compute_signature,
    features_for,
)
from .engine import PermissionEngine
from .matrix import DEFAULT_PERMISSION_MATRIX
from .modes import PermissionMode, apply_mode, resolve_mode
from .role_matrices import ROLE_PERMISSION_MATRICES
from .types import ActionCategory, PermissionLevel, PermissionResult

__all__ = [
    "ActionCategory",
    "ActionClassifier",
    "BucketState",
    "ConfidenceTier",
    "ContextRule",
    "DEFAULT_CONTEXT_RULES",
    "DEFAULT_PERMISSION_MATRIX",
    "DecisionOutcome",
    "INITIAL_BUCKET_STATE",
    "PermissionContext",
    "PermissionEngine",
    "PermissionLevel",
    "PermissionMode",
    "PermissionResult",
    "ROLE_PERMISSION_MATRICES",
    "RiskScoreRule",
    "RoleMatrixRule",
    "SIGNATURE_VERSION",
    "TimeOfDayRule",
    "TrustLevelRule",
    "apply_decision",
    "apply_mode",
    "compute_bucket_key",
    "compute_signature",
    "current_tier",
    "features_for",
    "resolve_mode",
]
