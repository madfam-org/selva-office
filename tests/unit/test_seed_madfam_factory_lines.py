"""Tests for the MADFAM factory-lines roster and its idempotent bootstrap plan."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "seed-madfam-factory-lines.py"
SKILLS_DIR = REPO_ROOT / "packages" / "skills" / "skill-definitions"

# Tools an autonomously-run factory-line agent must never hold through a skill.
FORBIDDEN_SKILL_TOOLS = {
    "send_email",
    "send_marketing_email",
    "whatsapp_send_template",
    "send_notification",
    "crm_update",
    "git_push",
    "git_create_pr",
}


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_factory_lines", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def seed() -> ModuleType:
    return _load_script()


@pytest.fixture(scope="module")
def roster(seed: ModuleType) -> dict:
    return seed.load_roster()


def test_roster_has_three_lines_plus_faap(roster: dict) -> None:
    ids = [line["id"] for line in roster["lines"]]
    assert ids == ["software", "geometry", "physical", "faap"]


def test_every_line_has_agents_and_a_factory_slug(roster: dict) -> None:
    for line in roster["lines"]:
        assert line["department"]["slug"].startswith("factory-")
        assert 1 <= len(line["agents"]) <= line["department"]["max_agents"]


def test_agent_skills_exist_and_hold_no_send_or_push_tools(roster: dict) -> None:
    for line in roster["lines"]:
        for agent in line["agents"]:
            for skill in agent["skill_ids"]:
                skill_md = SKILLS_DIR / skill / "SKILL.md"
                assert skill_md.exists(), f"{agent['name']}: unknown skill {skill}"
                text = skill_md.read_text(encoding="utf-8")
                header = text.split("---")[1]
                for tool in FORBIDDEN_SKILL_TOOLS:
                    assert f"- {tool}\n" not in header, f"{skill} grants {tool}"


def test_plan_on_empty_org_creates_everything(seed: ModuleType, roster: dict) -> None:
    plan = seed.plan_roster(roster, [], [])
    assert len(plan.departments_to_create) == 4
    assert len(plan.agents_to_create) == sum(len(x["agents"]) for x in roster["lines"])
    assert plan.conflicts == []


def test_plan_is_idempotent_when_everything_exists(seed: ModuleType, roster: dict) -> None:
    depts = [{"slug": x["department"]["slug"], "id": x["id"]} for x in roster["lines"]]
    agents = [{"name": a["name"]} for x in roster["lines"] for a in x["agents"]]
    plan = seed.plan_roster(roster, depts, agents)
    assert plan.departments_to_create == []
    assert plan.agents_to_create == []
    assert len(plan.existing) == len(depts) + len(agents)


def test_slug_owned_by_another_org_is_a_conflict(seed: ModuleType, roster: dict) -> None:
    plan = seed.plan_roster(roster, [], [], global_slugs={"factory-geometry"})
    assert any("factory-geometry" in c for c in plan.conflicts)
    created = {d["slug"] for d in plan.departments_to_create}
    assert "factory-geometry" not in created
    # The conflicted line's agents are not planned into a department we do not own.
    assert all(a["department_slug"] != "factory-geometry" for a in plan.agents_to_create)


def test_invalid_role_is_rejected(seed: ModuleType, tmp_path: Path) -> None:
    bad = tmp_path / "roster.yaml"
    bad.write_text(
        "schema: selva.factory-lines/v1\nlines:\n"
        "  - id: x\n    department: {slug: factory-x, name: X}\n"
        "    agents: [{name: A, role: wizard}]\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="invalid role"):
        seed.load_roster(bad)
