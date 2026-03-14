"""Tests for SkillRegistry.refresh() method."""

from __future__ import annotations

from pathlib import Path

from autoswarm_skills.registry import SkillRegistry

# Resolve to the real skill-definitions directory
SKILL_DEFS_DIR = Path(__file__).resolve().parent.parent / "skill-definitions"


def _write_skill(directory: Path, name: str, description: str = "A test skill.") -> Path:
    """Create a minimal SKILL.md file in a named subdirectory."""
    skill_dir = directory / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"allowed_tools: []\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"Instructions for {name}.\n",
        encoding="utf-8",
    )
    return skill_md


def test_refresh_clears_and_rediscovers(tmp_path: Path) -> None:
    """After refresh(), the registry should clear caches and re-discover skills."""
    _write_skill(tmp_path, "refresh-skill-a")
    _write_skill(tmp_path, "refresh-skill-b")

    registry = SkillRegistry(skills_dir=tmp_path)
    assert len(registry.list_skills()) == 2

    # Activate one to populate the definitions cache
    defn = registry.activate("refresh-skill-a")
    assert defn.meta.name == "refresh-skill-a"

    # Refresh should clear and re-discover
    registry.refresh()

    skills = registry.list_skills()
    assert len(skills) == 2
    names = {s.name for s in skills}
    assert names == {"refresh-skill-a", "refresh-skill-b"}


def test_refresh_picks_up_new_skills(tmp_path: Path) -> None:
    """Skills added after initial discovery are found after refresh()."""
    _write_skill(tmp_path, "existing-skill")

    registry = SkillRegistry(skills_dir=tmp_path)
    assert len(registry.list_skills()) == 1

    # Add a new skill after construction
    _write_skill(tmp_path, "new-skill")

    # Before refresh, the new skill is not visible
    assert registry.get_metadata("new-skill") is None

    # After refresh, it should appear
    registry.refresh()
    assert registry.get_metadata("new-skill") is not None
    assert len(registry.list_skills()) == 2


def test_refresh_previously_discovered_still_available(tmp_path: Path) -> None:
    """Previously discovered skills remain available after refresh()."""
    _write_skill(tmp_path, "stable-skill")

    registry = SkillRegistry(skills_dir=tmp_path)
    meta_before = registry.get_metadata("stable-skill")
    assert meta_before is not None
    assert meta_before.name == "stable-skill"

    registry.refresh()

    meta_after = registry.get_metadata("stable-skill")
    assert meta_after is not None
    assert meta_after.name == "stable-skill"


def test_refresh_clears_definition_cache(tmp_path: Path) -> None:
    """Activated (cached) definitions are cleared on refresh and reloaded on demand."""
    _write_skill(tmp_path, "cache-test")

    registry = SkillRegistry(skills_dir=tmp_path)
    defn1 = registry.activate("cache-test")

    registry.refresh()

    # After refresh, activate again: should be a new object (not cached)
    defn2 = registry.activate("cache-test")
    assert defn2.meta.name == "cache-test"
    assert defn1 is not defn2


def test_refresh_with_real_skills() -> None:
    """Refresh on the real skill-definitions directory retains all core skills."""
    registry = SkillRegistry(skills_dir=SKILL_DEFS_DIR)
    count_before = len(registry.list_skills())
    assert count_before >= 11  # Known core skills

    registry.refresh()

    count_after = len(registry.list_skills())
    assert count_after == count_before

    # Spot-check a known skill
    meta = registry.get_metadata("coding")
    assert meta is not None
    assert meta.name == "coding"
