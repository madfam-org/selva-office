"""The vendored impeccable skill: pin integrity, loading, UI/UX task routing."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

from selva_skills import impeccable
from selva_skills.parser import parse_skill_md
from selva_skills.registry import SkillRegistry
from selva_skills.types import SkillAudience

PKG = Path(__file__).resolve().parent.parent
SKILL_DEFS_DIR = PKG / "skill-definitions"
COMMUNITY_DIR = PKG / "community-skills"
ROOT = PKG.parents[1]
SCRIPT = ROOT / "scripts" / "vendor-impeccable.py"


def _vendor_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vendor_impeccable", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["vendor_impeccable"] = module
    spec.loader.exec_module(module)
    return module


# -- pin + vendored tree ----------------------------------------------------------


def test_vendored_tree_matches_pin_and_generated_skill_is_current() -> None:
    problems = _vendor_script().check_problems()
    assert problems == [], "run: python3 scripts/vendor-impeccable.py render\n" + "\n".join(
        problems
    )


def test_license_and_notice_are_vendored() -> None:
    license_text = (impeccable.VENDOR_DIR / "LICENSE").read_text(encoding="utf-8")
    assert "Apache License" in license_text and "Version 2.0" in license_text
    assert (impeccable.VENDOR_DIR / "NOTICE.md").is_file()
    assert impeccable.load_pin()["license"] == "Apache-2.0"


def test_pin_is_a_specific_release() -> None:
    pin = impeccable.load_pin()
    assert pin["skill_tag"] == f"skill-v{pin['npm_version']}"
    assert len(pin["commit"]) == 40
    assert pin["engine_version"].count(".") == 2
    for target in ("linux-x64", "linux-arm64"):
        assert pin["engine_packages"][target]["integrity"].startswith("sha512-")


def test_hand_edit_of_vendored_file_is_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _vendor_script()
    vendor_root = tmp_path / "vendor"
    shutil.copytree(impeccable.VENDOR_DIR.parent, vendor_root)
    skill_md = tmp_path / "SKILL.md"
    shutil.copy2(SKILL_DEFS_DIR / "impeccable" / "SKILL.md", skill_md)
    monkeypatch.setattr(script, "VENDOR_DIR", vendor_root / "impeccable")
    monkeypatch.setattr(script, "PIN_PATH", vendor_root / "impeccable.pin.json")
    monkeypatch.setattr(script, "ADAPTER_PATH", vendor_root / "impeccable.adapter.md")
    monkeypatch.setattr(script, "SKILL_MD_PATH", skill_md)
    assert script.check_problems() == []

    polish = vendor_root / "impeccable" / "reference" / "polish.md"
    polish.write_text(polish.read_text(encoding="utf-8") + "\nlocal tweak\n", encoding="utf-8")
    assert any("changed by hand" in p and "polish.md" in p for p in script.check_problems())


# -- the skill itself ----------------------------------------------------------------


def test_skill_parses_for_tenants_without_widening_permissions() -> None:
    meta, body = parse_skill_md(SKILL_DEFS_DIR / "impeccable" / "SKILL.md")
    assert meta.name == impeccable.IMPECCABLE_SKILL_NAME
    assert meta.audience == SkillAudience.TENANT
    assert meta.license == "Apache-2.0"
    # The skill adds the detector and file reads only; it must never grant
    # file_write or other side-effect categories to whoever loads it.
    assert set(meta.allowed_tools) == {"file_read", "impeccable_detect"}
    assert meta.metadata["upstream_version"] == impeccable.load_pin()["npm_version"]
    assert "Impeccable in the Selva harness" in body
    assert "## Upstream skill: impeccable" in body
    assert "## Upstream reference: craft-floor.md (verbatim)" in body


def test_skill_body_carries_upstream_text_verbatim() -> None:
    _, body = parse_skill_md(SKILL_DEFS_DIR / "impeccable" / "SKILL.md")
    upstream = (impeccable.VENDOR_DIR / "SKILL.md").read_text(encoding="utf-8")
    upstream_body = upstream.split("---", 2)[2].strip()
    craft_floor = (impeccable.VENDOR_DIR / "reference" / "craft-floor.md").read_text(
        encoding="utf-8"
    )
    assert upstream_body in body
    assert craft_floor.strip() in body


def test_registry_builds_prompt_for_tenant_and_platform_swarms() -> None:
    registry = SkillRegistry(skills_dir=SKILL_DEFS_DIR, community_skills_dir=COMMUNITY_DIR)
    assert registry.get_metadata("impeccable") is not None
    for audience in (SkillAudience.TENANT, SkillAudience.PLATFORM):
        prompt = registry.build_system_prompt(["coding", "impeccable"], audience=audience)
        assert "## Skill: impeccable" in prompt
        assert "impeccable_detect" in prompt
    assert "impeccable_detect" in registry.get_allowed_tools(["impeccable"])


# -- UI/UX task routing -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("graph_type", "payload", "description", "expected"),
    [
        ("coding", {}, "Polish the onboarding empty state component", True),
        ("coding", {}, "Make the pricing page responsive on mobile", True),
        ("coding", {}, "Fix the Redis pool reconnect backoff", False),
        ("coding", {"ui_ux": True}, "Refactor", True),
        ("coding", {"ui_ux": False}, "Redesign the landing page", False),
        ("research", {"impeccable_command": "critique"}, "Review our signup", True),
        ("research", {}, "Compare dashboard vendors", False),
        ("crm", {}, "Send the follow-up email", False),
    ],
)
def test_is_ui_ux_task(
    graph_type: str, payload: dict[str, object], description: str, expected: bool
) -> None:
    assert impeccable.is_ui_ux_task(graph_type, payload, description) is expected


def test_with_impeccable_skill_is_idempotent() -> None:
    assert impeccable.with_impeccable_skill(["coding"]) == ["coding", "impeccable"]
    assert impeccable.with_impeccable_skill(["impeccable", "coding"]) == ["impeccable", "coding"]


def test_ui_files_filters_by_extension() -> None:
    assert impeccable.ui_files(
        ["a.py", "web/Page.TSX", "s.css", "web/Page.TSX", "x.ts", "v.vue", "b.blade.php"]
    ) == ["web/Page.TSX", "s.css", "v.vue", "b.blade.php"]


def test_all_upstream_commands_have_a_reference() -> None:
    commands = impeccable.commands()
    meta = json.loads(
        (impeccable.VENDOR_DIR / "scripts" / "command-metadata.json").read_text(encoding="utf-8")
    )
    assert commands == tuple(meta)
    for command in commands:
        section = impeccable.command_reference(command)
        assert section.startswith(f"## Skill reference: impeccable `{command}`")
        assert len(section) > 300


def test_native_reference_variant() -> None:
    assert "reference/audit.native.md" in impeccable.command_reference("audit", native=True)
    assert "reference/polish.md" in impeccable.command_reference("polish", native=True)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("polish", "polish"),
        ("/impeccable audit apps/web", "audit"),
        (" Critique ", "critique"),
        ("teach", "init"),
        ("", None),
        (None, None),
    ],
)
def test_requested_command(raw: object, expected: str | None) -> None:
    assert impeccable.requested_command({"impeccable_command": raw}) == expected


def test_unknown_command_fails_visibly() -> None:
    with pytest.raises(ValueError, match="unknown impeccable_command"):
        impeccable.requested_command({"impeccable_command": "make-it-pop"})
