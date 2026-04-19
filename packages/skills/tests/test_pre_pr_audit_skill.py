"""Regression tests for the pre-pr-audit skill's metadata + wiring."""

from __future__ import annotations

from pathlib import Path

from selva_skills.parser import parse_skill_md
from selva_skills.registry import SkillRegistry
from selva_skills.types import SkillAudience

SKILL_DEFS_DIR = Path(__file__).resolve().parent.parent / "skill-definitions"
COMMUNITY_DIR = Path(__file__).resolve().parent.parent / "community-skills"


def test_pre_pr_audit_skill_definition_exists() -> None:
    skill_dir = SKILL_DEFS_DIR / "pre-pr-audit"
    assert skill_dir.exists(), "pre-pr-audit/ must exist under skill-definitions/"
    assert (skill_dir / "SKILL.md").exists(), "SKILL.md must exist"


def test_pre_pr_audit_skill_parses() -> None:
    meta, body = parse_skill_md(SKILL_DEFS_DIR / "pre-pr-audit" / "SKILL.md")
    assert meta.name == "pre-pr-audit"
    assert meta.audience == SkillAudience.TENANT
    # Instructions body is non-trivial — the skill's teeth are in the markdown.
    assert len(body) > 500


def test_pre_pr_audit_skill_grants_minimum_tool_surface() -> None:
    """The skill needs at least these tools to do its job:
    - file_read (inspect diffs, CLAUDE.md, .env.example)
    - bash_execute (run `git diff`, `pytest`, `grep`)
    For remediation actions it also needs file_write.
    Without these three it can report gaps but can't close them.
    """
    meta, _ = parse_skill_md(SKILL_DEFS_DIR / "pre-pr-audit" / "SKILL.md")
    tools = set(meta.allowed_tools)
    assert {"file_read", "bash_execute", "file_write"}.issubset(tools)


def test_pre_pr_audit_registered_for_tenant_swarms() -> None:
    """Tenant swarms MUST be able to activate this — it's a general SWE practice,
    not platform-specific. If someone ever marks it platform, this fails loudly.
    """
    registry = SkillRegistry(skills_dir=SKILL_DEFS_DIR, community_skills_dir=COMMUNITY_DIR)
    meta = registry.get_metadata("pre-pr-audit")
    assert meta is not None
    assert meta.audience == SkillAudience.TENANT
    # Activate under a tenant swarm context — must not raise.
    activated = registry.activate("pre-pr-audit", audience=SkillAudience.TENANT)
    assert activated is not None
