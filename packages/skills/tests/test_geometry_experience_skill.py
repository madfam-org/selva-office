"""The geometry authoring definition loads without granting runtime execution."""

import subprocess
import sys
from pathlib import Path

from selva_skills.registry import SkillRegistry
from selva_skills.types import SkillAudience

SKILL = Path(__file__).resolve().parents[1] / "skill-definitions" / "madfam-geometry-experience"


def test_geometry_skill_loads_without_broadening_tool_permissions():
    registry = SkillRegistry(skills_dir=SKILL, community_enabled=False)
    definition = registry.activate("madfam-geometry-experience", audience=SkillAudience.TENANT)
    assert definition.meta.metadata["version"] == "0.5.0-draft"
    assert definition.meta.metadata["maturity"] == "local-draft"
    assert registry.get_allowed_tools([definition.meta.name]) == []
    assert definition.skill_dir == SKILL


def test_geometry_skill_resources_are_packaged_with_the_definition():
    for relative in (
        "references/ownership-and-adapters.md",
        "references/anatomy-and-evaluation.md",
        "references/native-factory-pilot.md",
        "references/cross-platform-pilot.md",
        "references/catalogue-evaluation.md",
        "scripts/verify-catalogue.py",
        "scripts/verify-study.mjs",
        "scripts/verify-bundle.py",
        "agents/openai.yaml",
    ):
        assert (SKILL / relative).is_file()


def test_geometry_bundle_integrity_regressions_execute_without_native_runtimes():
    result = subprocess.run(
        [sys.executable, str(SKILL / "scripts/test_verify_bundle.py")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_geometry_catalogue_integrity_boundaries_execute_without_native_runtimes():
    result = subprocess.run(
        [sys.executable, str(SKILL / "scripts/test_verify_catalogue.py")],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
