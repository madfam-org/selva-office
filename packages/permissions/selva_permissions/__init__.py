"""AutoSwarm Permissions -- HITL permission system with action classification."""

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
from .role_matrices import ROLE_PERMISSION_MATRICES

__all__ = [
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
    "RiskScoreRule",
    "ROLE_PERMISSION_MATRICES",
    "RoleMatrixRule",
    "SIGNATURE_VERSION",
    "TimeOfDayRule",
    "TrustLevelRule",
    "apply_decision",
    "compute_bucket_key",
    "compute_signature",
    "current_tier",
    "features_for",
]
