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
    """The skill needs at least:
    - file_read / file_write (inspect + remediate docs, .env.example, CLAUDE.md)
    - bash_execute (grep, ad-hoc git)
    - lint_and_typecheck (style pass)
    - test_coverage_for_diff (coverage pass)
    - git_create_pr (gated PR submission)
    - deploy_preflight (manifest hygiene pass)
    Without these the skill can't do its job as a pre-submission gate.
    """
    meta, _ = parse_skill_md(SKILL_DEFS_DIR / "pre-pr-audit" / "SKILL.md")
    tools = set(meta.allowed_tools)
    required = {
        "file_read",
        "file_write",
        "bash_execute",
        "lint_and_typecheck",
        "test_coverage_for_diff",
        "git_create_pr",
        "deploy_preflight",
    }
    missing = required - tools
    assert not missing, f"skill missing required tools: {missing}"


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
