"""Per-role permission matrices for agent specialization.

Each role has restrictions on actions outside its domain. These matrices
are used by ``RoleMatrixRule`` to escalate permissions when an agent
attempts an action it shouldn't normally perform.
"""

from __future__ import annotations

from .types import ActionCategory, PermissionLevel

ROLE_PERMISSION_MATRICES: dict[str, dict[ActionCategory, PermissionLevel]] = {
    "reviewer": {
        # Reviewers can read and comment but should not push code.
        ActionCategory.GIT_PUSH: PermissionLevel.DENY,
        ActionCategory.DEPLOY: PermissionLevel.DENY,
    },
    "researcher": {
        # Researchers gather info; they should not send external comms.
        ActionCategory.EMAIL_SEND: PermissionLevel.DENY,
        ActionCategory.CRM_UPDATE: PermissionLevel.DENY,
    },
    "coder": {
        # Coders write code but should not update CRM directly.
        ActionCategory.CRM_UPDATE: PermissionLevel.DENY,
        ActionCategory.EMAIL_SEND: PermissionLevel.ASK,
    },
    "planner": {
        # Planners coordinate but should not execute directly.
        ActionCategory.BASH_EXECUTE: PermissionLevel.ASK,
        ActionCategory.GIT_PUSH: PermissionLevel.ASK,
    },
    "crm": {
        # CRM agents should not push code or deploy.
        ActionCategory.GIT_PUSH: PermissionLevel.DENY,
        ActionCategory.DEPLOY: PermissionLevel.DENY,
        ActionCategory.BASH_EXECUTE: PermissionLevel.DENY,
    },
    "support": {
        # Support agents have read-heavy access; restrict destructive ops.
        ActionCategory.GIT_PUSH: PermissionLevel.DENY,
        ActionCategory.DEPLOY: PermissionLevel.DENY,
        ActionCategory.FILE_WRITE: PermissionLevel.ASK,
    },
}
