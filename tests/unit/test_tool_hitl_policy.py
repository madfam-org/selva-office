"""Every built-in tool carries an explicit HITL policy, and the inventory doc is current."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "generate-tool-hitl-inventory.py"


@pytest.fixture()
def armed_builtin_names(monkeypatch: pytest.MonkeyPatch) -> set[str]:
    # Ship-dark social tools only register when armed; arm them so they are
    # covered too.
    monkeypatch.setenv("SELVA_X_POST_ENABLED", "1")
    monkeypatch.setenv("SELVA_LINKEDIN_POST_ENABLED", "1")
    from selva_tools.builtins import get_builtin_tools

    return {tool.name for tool in get_builtin_tools()}


def test_every_builtin_tool_has_explicit_policy(armed_builtin_names: set[str]) -> None:
    from selva_permissions.tool_policy import BUILTIN_TOOL_POLICY

    missing = sorted(armed_builtin_names - set(BUILTIN_TOOL_POLICY))
    assert missing == [], (
        "New built-in tools need an entry in "
        "packages/permissions/selva_permissions/tool_policy.py "
        f"(side-effect class + ActionCategory): {missing}"
    )


def test_policy_has_no_stale_entries(armed_builtin_names: set[str]) -> None:
    from selva_permissions.tool_policy import BUILTIN_TOOL_POLICY, NON_REGISTRY_TOOL_NAMES

    stale = sorted(set(BUILTIN_TOOL_POLICY) - armed_builtin_names - NON_REGISTRY_TOOL_NAMES)
    assert stale == []


def test_inventory_doc_is_current(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("SELVA_X_POST_ENABLED", "SELVA_LINKEDIN_POST_ENABLED"):
        monkeypatch.setenv(var, "1")
    spec = importlib.util.spec_from_file_location("gen_tool_hitl_inventory", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected = module.build()
    current = (ROOT / "docs" / "TOOL_HITL_INVENTORY.md").read_text()
    assert current == expected, "run: uv run python scripts/generate-tool-hitl-inventory.py"
