"""Permission modes — 3-tier presets on top of the fine-grained matrix.

Absorbed from `ultraworkers/claw-code` as a *capability surface* (names and
semantics), not as code. Behaviour is overlaid on the existing
:class:`PermissionMatrix` so day-zero contracts don't change.

Contract with the agent runtime:

    1. The default mode is :data:`PermissionMode.WORKSPACE_WRITE`. It
       matches the out-of-the-box matrix shipped today.
    2. An autonomous agent *never* prompts the human for a tool call that
       evaluates to :class:`PermissionLevel.ALLOW`.
    3. ``ASK`` still triggers HITL via LangGraph ``interrupt()`` exactly
       as before. Modes widen or narrow the set of categories that
       resolve to ``ASK`` or ``ALLOW``, but they do not change how ``ASK``
       is satisfied.
    4. ``DANGER_FULL_ACCESS`` removes every ``ASK`` gate. It is intended
       for ephemeral sandboxes only — NEVER production tenants. Callers
       that try to select it in a production context must be refused by
       the dispatch layer; this module cannot enforce that alone.

Wire-up:

    * Dispatch layer reads ``mode`` from the task payload (or falls back
      to the env default).
    * ``apply_mode()`` returns the effective matrix that the
      :class:`PermissionEngine` should use for that task.
    * The engine's existing per-action evaluation path is unchanged.
"""

from __future__ import annotations

import os
from enum import StrEnum

from .matrix import DEFAULT_PERMISSION_MATRIX
from .types import ActionCategory, PermissionLevel


class PermissionMode(StrEnum):
    """High-level permission posture for a single task run.

    Names and semantics mirror the claw-code surface so agent-facing docs
    stay interchangeable:

    - ``READ_ONLY``: reads are ``ALLOW``, all writes/execs/sends are
      ``DENY``. Nothing can mutate anything.
    - ``WORKSPACE_WRITE``: the default. File writes and bash are ``ASK``;
      the rest of the matrix is unchanged.
    - ``DANGER_FULL_ACCESS``: every category becomes ``ALLOW``. Use only
      in hermetic sandboxes.
    """

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    DANGER_FULL_ACCESS = "danger-full-access"


# Actions that are *always* reads. Mode adjustments leave these alone.
_ALWAYS_READ: frozenset[ActionCategory] = frozenset(
    {
        ActionCategory.FILE_READ,
        ActionCategory.API_CALL,
        ActionCategory.INFRASTRUCTURE_MONITOR,
    }
)

# Actions that are *always* writes/mutations (for READ_ONLY evaluation).
_MUTATING_ACTIONS: frozenset[ActionCategory] = frozenset(
    {
        ActionCategory.FILE_WRITE,
        ActionCategory.BASH_EXECUTE,
        ActionCategory.GIT_COMMIT,
        ActionCategory.GIT_PUSH,
        ActionCategory.EMAIL_SEND,
        ActionCategory.CRM_UPDATE,
        ActionCategory.DEPLOY,
        ActionCategory.BILLING_WRITE,
        ActionCategory.MARKETING_SEND,
        ActionCategory.INFRASTRUCTURE_EXEC,
        ActionCategory.SECRET_MANAGEMENT,
        ActionCategory.DATABASE_MIGRATION,
    }
)


def _read_only_matrix() -> dict[ActionCategory, PermissionLevel]:
    """Every mutation DENIED; reads ALLOW."""
    return {
        action: PermissionLevel.ALLOW
        if action in _ALWAYS_READ
        else PermissionLevel.DENY
        for action in ActionCategory
    }


def _workspace_write_matrix() -> dict[ActionCategory, PermissionLevel]:
    """Default matrix — unchanged from the current shipping default."""
    # Copy so callers can't mutate the module-level dict.
    return dict(DEFAULT_PERMISSION_MATRIX)


def _danger_full_access_matrix() -> dict[ActionCategory, PermissionLevel]:
    """Every action ALLOW. No HITL gates at all."""
    return {action: PermissionLevel.ALLOW for action in ActionCategory}


_MODE_BUILDERS = {
    PermissionMode.READ_ONLY: _read_only_matrix,
    PermissionMode.WORKSPACE_WRITE: _workspace_write_matrix,
    PermissionMode.DANGER_FULL_ACCESS: _danger_full_access_matrix,
}


def apply_mode(
    mode: PermissionMode,
    *,
    overrides: dict[ActionCategory, PermissionLevel] | None = None,
) -> dict[ActionCategory, PermissionLevel]:
    """Return the effective matrix for ``mode`` with optional per-task overrides.

    Overrides always win. This is how the dispatch layer honours a
    short-lived escalation (e.g. "allow DEPLOY for this one task even in
    read-only mode") without rewriting the mode itself.
    """
    builder = _MODE_BUILDERS.get(mode)
    if builder is None:
        raise ValueError(f"unknown PermissionMode: {mode!r}")
    matrix = builder()
    if overrides:
        matrix.update(overrides)
    return matrix


def resolve_mode(
    requested: str | PermissionMode | None,
    *,
    env_var: str = "SELVA_PERMISSION_MODE",
    default: PermissionMode = PermissionMode.WORKSPACE_WRITE,
) -> PermissionMode:
    """Pick a mode from (in priority order) caller request → env → default.

    Values that don't match a known mode raise ``ValueError`` so typos
    surface at dispatch time instead of silently dropping to default.
    """
    if requested is not None:
        if isinstance(requested, PermissionMode):
            return requested
        try:
            return PermissionMode(requested)
        except ValueError as exc:
            raise ValueError(
                f"unknown permission mode {requested!r}; "
                f"valid: {[m.value for m in PermissionMode]}"
            ) from exc

    env_val = os.environ.get(env_var)
    if env_val:
        try:
            return PermissionMode(env_val)
        except ValueError as exc:
            raise ValueError(
                f"{env_var}={env_val!r} is not a valid mode; "
                f"valid: {[m.value for m in PermissionMode]}"
            ) from exc

    return default


__all__ = [
    "PermissionMode",
    "apply_mode",
    "resolve_mode",
]
