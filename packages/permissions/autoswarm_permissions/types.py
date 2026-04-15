"""Core types for the HITL permission system."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class PermissionLevel(StrEnum):
    """Possible permission decisions for an action."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


class ActionCategory(StrEnum):
    """Categories of actions that agents can request."""

    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    BASH_EXECUTE = "bash_execute"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    EMAIL_SEND = "email_send"
    CRM_UPDATE = "crm_update"
    DEPLOY = "deploy"
    API_CALL = "api_call"
    BILLING_WRITE = "billing_write"
    MARKETING_SEND = "marketing_send"
    INFRASTRUCTURE_EXEC = "infrastructure_exec"
    SECRET_MANAGEMENT = "secret_management"
    INFRASTRUCTURE_MONITOR = "infra_monitor"
    DATABASE_MIGRATION = "database_migration"


class PermissionResult(BaseModel):
    """Outcome of evaluating a permission request."""

    action_category: ActionCategory
    level: PermissionLevel
    requires_approval: bool
    reason: str
