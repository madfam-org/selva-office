"""Repo-context-aware system prompts for coding graph nodes."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_CONTEXT_LINES = 50


def _read_repo_context(repo_path: str | None) -> dict[str, str]:
    """Read lightweight repo context: top-level listing and key files.

    Returns a dict with keys ``listing``, ``readme``, ``claude_md`` (any may
    be empty strings).
    """
    ctx: dict[str, str] = {"listing": "", "readme": "", "claude_md": ""}
    if not repo_path:
        return ctx

    root = Path(repo_path)
    if not root.is_dir():
        return ctx

    # Top-level listing
    try:
        entries = sorted(p.name for p in root.iterdir() if not p.name.startswith("."))
        ctx["listing"] = "\n".join(entries[:40])
    except OSError:
        pass

    # README excerpt
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme = root / name
        if readme.is_file():
            try:
                lines = readme.read_text(errors="replace").splitlines()[:_MAX_CONTEXT_LINES]
                ctx["readme"] = "\n".join(lines)
            except OSError:
                pass
            break

    # CLAUDE.md excerpt (project conventions)
    claude_md = root / "CLAUDE.md"
    if claude_md.is_file():
        try:
            lines = claude_md.read_text(errors="replace").splitlines()[:_MAX_CONTEXT_LINES]
            ctx["claude_md"] = "\n".join(lines)
        except OSError:
            pass

    return ctx


def _detect_language(repo_path: str | None) -> str:
    """Best-effort language detection from file extensions."""
    if not repo_path:
        return "unknown"
    root = Path(repo_path)
    if not root.is_dir():
        return "unknown"

    ext_counts: dict[str, int] = {}
    try:
        for p in root.rglob("*"):
            if p.is_file() and not any(
                part.startswith(".") for part in p.parts
            ):
                ext = p.suffix.lower()
                if ext in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".rb"):
                    ext_counts[ext] = ext_counts.get(ext, 0) + 1
    except OSError:
        pass

    if not ext_counts:
        return "unknown"

    ext_to_lang = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript/React",
        ".js": "JavaScript",
        ".jsx": "JavaScript/React",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".rb": "Ruby",
    }
    top_ext = max(ext_counts, key=ext_counts.get)  # type: ignore[arg-type]
    return ext_to_lang.get(top_ext, "unknown")


def build_plan_prompt(
    description: str,
    repo_path: str | None = None,
    skill_ctx: str = "",
) -> str:
    """Build a system prompt for the plan() node with repo context."""
    ctx = _read_repo_context(repo_path)
    lang = _detect_language(repo_path)

    sections = [
        "You are a senior developer creating an implementation plan.",
        "Break the task into an ordered list of concrete file changes.",
        "Return a JSON object with keys: 'description' (string) and 'steps' (array of strings).",
    ]

    if lang != "unknown":
        sections.append(f"Primary language: {lang}.")

    if ctx["listing"]:
        sections.append(f"Repository top-level files:\n```\n{ctx['listing']}\n```")

    if ctx["readme"]:
        sections.append(
            f"README excerpt (first {_MAX_CONTEXT_LINES} lines):\n"
            f"```\n{ctx['readme']}\n```"
        )

    if ctx["claude_md"]:
        sections.append(
            f"Project conventions (CLAUDE.md excerpt):\n"
            f"```\n{ctx['claude_md']}\n```"
        )

    base = "\n\n".join(sections)
    if skill_ctx:
        return f"{skill_ctx}\n\n{base}"
    return base


def build_implement_prompt(
    step: str,
    iteration: int,
    repo_path: str | None = None,
    worktree_path: str | None = None,
    skill_ctx: str = "",
) -> str:
    """Build a system prompt for the implement() node with strict JSON instructions."""
    ctx = _read_repo_context(worktree_path or repo_path)

    sections = [
        "You are a senior developer implementing code changes.",
        "IMPORTANT: Return ONLY a JSON object with key 'files' containing an array of objects.",
        "Each object must have 'path' (relative to project root) and 'content' (full file text).",
        'Example: {"files": [{"path": "src/main.py", "content": "# full file content..."}]}',
        "Do NOT return markdown, explanations, or anything other than the JSON object.",
    ]

    if ctx["listing"]:
        sections.append(f"Existing project files:\n```\n{ctx['listing']}\n```")

    if ctx["claude_md"]:
        sections.append(
            f"Project conventions (CLAUDE.md excerpt):\n"
            f"```\n{ctx['claude_md']}\n```"
        )

    sections.append(
        "Prefer editing existing files over creating new ones. "
        "Match the project's existing coding style and conventions."
    )

    base = "\n\n".join(sections)
    if skill_ctx:
        return f"{skill_ctx}\n\n{base}"
    return base


def build_review_prompt(
    changes: str,
    skill_ctx: str = "",
) -> str:
    """Build a system prompt for the review() node with enhanced criteria."""
    sections = [
        "You are a thorough code reviewer. Evaluate the changes for:",
        "1. Correctness — does the code do what the task requires?",
        "2. Security — path traversal, injection, credential exposure?",
        "3. Style — matches project conventions and language idioms?",
        "4. Completeness — are all required files modified? Any missing imports?",
        "",
        "Return JSON with keys: 'changes_reviewed' (int), 'issues_found' (int), "
        "'recommendation' ('approve' or 'revise'), 'issues' (array of strings, optional).",
    ]

    base = "\n".join(sections)
    if skill_ctx:
        return f"{skill_ctx}\n\n{base}"
    return base
