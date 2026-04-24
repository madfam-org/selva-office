"""Parser for AgentSkills-standard SKILL.md files."""

from __future__ import annotations

from pathlib import Path

import yaml

from .types import SkillMetadata


def parse_skill_md(path: Path) -> tuple[SkillMetadata, str]:
    """Parse a SKILL.md file into metadata and markdown body.

    The file must start with a YAML frontmatter block delimited by ``---`` fences.
    The ``name`` field in the frontmatter must match the parent directory name.

    Args:
        path: Absolute path to the SKILL.md file.

    Returns:
        A tuple of (SkillMetadata, instructions_body).

    Raises:
        ValueError: If the file format is invalid or name mismatches directory.
    """
    text = path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise ValueError(f"{path}: SKILL.md must start with '---' YAML frontmatter fence")

    # Split on the closing fence
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"{path}: SKILL.md must have opening and closing '---' fences")

    frontmatter_raw = parts[1].strip()
    body = parts[2].strip()

    frontmatter = yaml.safe_load(frontmatter_raw)
    if not isinstance(frontmatter, dict):
        raise ValueError(f"{path}: YAML frontmatter must be a mapping")

    meta = SkillMetadata(**frontmatter)

    # Validate name matches parent directory
    expected_name = path.parent.name
    if meta.name != expected_name:
        raise ValueError(
            f"{path}: skill name '{meta.name}' does not match directory name '{expected_name}'"
        )

    return meta, body


def parse_skill_md_string(content: str) -> tuple[SkillMetadata, str]:
    """Parse YAML frontmatter from a raw string (no file/directory validation).

    Unlike :func:`parse_skill_md`, this function does not require a file on disk
    and does not validate that the skill ``name`` matches a parent directory.

    Args:
        content: Raw SKILL.md text with ``---`` delimited YAML frontmatter.

    Returns:
        A tuple of (SkillMetadata, instructions_body).

    Raises:
        ValueError: If the content format is invalid.
    """
    if not content.startswith("---"):
        raise ValueError("Content must start with '---' YAML frontmatter fence")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Content must have opening and closing '---' fences")

    frontmatter_raw = parts[1].strip()
    body = parts[2].strip()

    frontmatter = yaml.safe_load(frontmatter_raw)
    if not isinstance(frontmatter, dict):
        raise ValueError("YAML frontmatter must be a mapping")

    meta = SkillMetadata(**frontmatter)
    return meta, body
