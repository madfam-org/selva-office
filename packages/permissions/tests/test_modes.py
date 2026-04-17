"""Tests for permission modes (read-only / workspace-write / danger-full-access)."""

from __future__ import annotations

import pytest

from autoswarm_permissions import (
    ActionCategory,
    PermissionLevel,
    PermissionMode,
    apply_mode,
    resolve_mode,
)
from autoswarm_permissions.matrix import DEFAULT_PERMISSION_MATRIX


# -- apply_mode -------------------------------------------------------------


def test_read_only_denies_every_mutation():
    matrix = apply_mode(PermissionMode.READ_ONLY)
    for action in ActionCategory:
        if action in (
            ActionCategory.FILE_READ,
            ActionCategory.API_CALL,
            ActionCategory.INFRASTRUCTURE_MONITOR,
        ):
            assert matrix[action] is PermissionLevel.ALLOW, action
        else:
            assert matrix[action] is PermissionLevel.DENY, action


def test_workspace_write_equals_default_shipping_matrix():
    matrix = apply_mode(PermissionMode.WORKSPACE_WRITE)
    # Snapshot compare against the shipping default. Divergence means
    # somebody changed default behaviour via the mode shim — bad.
    assert matrix == dict(DEFAULT_PERMISSION_MATRIX)


def test_danger_full_access_allows_everything():
    matrix = apply_mode(PermissionMode.DANGER_FULL_ACCESS)
    for action in ActionCategory:
        assert matrix[action] is PermissionLevel.ALLOW, action


def test_workspace_write_is_default_for_empty_overrides():
    assert apply_mode(PermissionMode.WORKSPACE_WRITE, overrides=None) == apply_mode(
        PermissionMode.WORKSPACE_WRITE, overrides={}
    )


def test_overrides_win_over_mode():
    matrix = apply_mode(
        PermissionMode.READ_ONLY,
        overrides={ActionCategory.DEPLOY: PermissionLevel.ASK},
    )
    # Read-only would DENY deploy; the override must promote it to ASK.
    assert matrix[ActionCategory.DEPLOY] is PermissionLevel.ASK
    # Other mutations stay DENY.
    assert matrix[ActionCategory.FILE_WRITE] is PermissionLevel.DENY


def test_apply_mode_returns_fresh_dict_each_call():
    a = apply_mode(PermissionMode.WORKSPACE_WRITE)
    a[ActionCategory.FILE_WRITE] = PermissionLevel.ALLOW
    b = apply_mode(PermissionMode.WORKSPACE_WRITE)
    # Mutating the first result must not bleed into subsequent calls.
    assert b[ActionCategory.FILE_WRITE] is PermissionLevel.ASK


def test_apply_mode_rejects_unknown_mode():
    with pytest.raises(ValueError):
        apply_mode("not-a-mode")  # type: ignore[arg-type]


# -- resolve_mode -----------------------------------------------------------


def test_resolve_mode_prefers_explicit_argument(monkeypatch):
    monkeypatch.setenv("AUTOSWARM_PERMISSION_MODE", "danger-full-access")
    assert resolve_mode("read-only") is PermissionMode.READ_ONLY


def test_resolve_mode_falls_back_to_env(monkeypatch):
    monkeypatch.setenv("AUTOSWARM_PERMISSION_MODE", "danger-full-access")
    assert resolve_mode(None) is PermissionMode.DANGER_FULL_ACCESS


def test_resolve_mode_default_when_nothing_set(monkeypatch):
    monkeypatch.delenv("AUTOSWARM_PERMISSION_MODE", raising=False)
    assert resolve_mode(None) is PermissionMode.WORKSPACE_WRITE


def test_resolve_mode_accepts_enum_input():
    assert resolve_mode(PermissionMode.READ_ONLY) is PermissionMode.READ_ONLY


def test_resolve_mode_rejects_unknown_string(monkeypatch):
    monkeypatch.delenv("AUTOSWARM_PERMISSION_MODE", raising=False)
    with pytest.raises(ValueError, match="unknown permission mode"):
        resolve_mode("super-duper-mode")


def test_resolve_mode_rejects_garbage_env(monkeypatch):
    monkeypatch.setenv("AUTOSWARM_PERMISSION_MODE", "totally-bogus")
    with pytest.raises(ValueError, match="AUTOSWARM_PERMISSION_MODE"):
        resolve_mode(None)
