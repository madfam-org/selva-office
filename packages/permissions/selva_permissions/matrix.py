"""Default permission matrix for the HITL system.

The matrix maps each action category to a default permission level.
Actions marked ASK require human-in-the-loop approval before execution.
"""

from __future__ import annotations

from .types import ActionCategory, PermissionLevel

DEFAULT_PERMISSION_MATRIX: dict[ActionCategory, PermissionLevel] = {
    ActionCategory.FILE_READ: PermissionLevel.ALLOW,
    ActionCategory.FILE_WRITE: PermissionLevel.ASK,
    ActionCategory.BASH_EXECUTE: PermissionLevel.ASK,
    ActionCategory.GIT_COMMIT: PermissionLevel.ASK,
    ActionCategory.GIT_PUSH: PermissionLevel.ASK,
    ActionCategory.EMAIL_SEND: PermissionLevel.ASK,
    ActionCategory.CRM_UPDATE: PermissionLevel.ASK,
    ActionCategory.DEPLOY: PermissionLevel.ASK,
    ActionCategory.API_CALL: PermissionLevel.ALLOW,
    ActionCategory.BILLING_WRITE: PermissionLevel.ASK,
    ActionCategory.MARKETING_SEND: PermissionLevel.ASK,
    ActionCategory.INFRASTRUCTURE_EXEC: PermissionLevel.ASK,
    ActionCategory.SECRET_MANAGEMENT: PermissionLevel.ASK,
    ActionCategory.INFRASTRUCTURE_MONITOR: PermissionLevel.ALLOW,
    ActionCategory.DATABASE_MIGRATION: PermissionLevel.ASK,
    # RFC 0005: default is ASK; the write_kubernetes_secret tool reads
    # SELVA_ENV at call time and escalates to ASK_DUAL for prod or
    # relaxes to ALLOW for dev. Keeping the default at ASK means
    # *unknown* callers fail-closed to human approval.
    ActionCategory.K8S_SECRET_WRITE: PermissionLevel.ASK,
}
