"""
Gap 5: Project Context Files — AGENTS.md / .autoswarm.md loader

Scans a workspace root for project-level context files and injects them
into ACP system prompts, mirroring Hermes Agent's AGENTS.md / .hermes.md
convention for per-project grounding.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Files scanned in priority order (later files take precedence)
_CONTEXT_SOURCES = [
    "CLAUDE.md",       # Cross-tool compatibility (read-only passthrough)
    "GEMINI.md",       # Cross-tool compatibility
    "AGENTS.md",       # Project-level architecture / agent instructions
    ".autoswarm.md",   # Workspace-local override (highest priority)
]

_MAX_CHARS_PER_FILE = 32_000  # ~8,000 tokens at 4 chars/token


class ContextFileLoader:
    """
    Scans a workspace root for AutoSwarm-compatible context files and
    returns their concatenated content for injection into system prompts.
    """

    def __init__(self, max_chars_per_file: int = _MAX_CHARS_PER_FILE) -> None:
        self._max_chars = max_chars_per_file

    def load_context(self, workspace_path: str) -> str:
        """
        Scan *workspace_path* for context files and return their contents.

        Returns:
            Formatted context string ready for injection into a system prompt,
            or empty string if no context files are found.
        """
        root = Path(workspace_path)
        if not root.exists() or not root.is_dir():
            logger.debug("ContextFileLoader: workspace %s does not exist.", workspace_path)
            return ""

        sections: list[str] = []
        for filename in _CONTEXT_SOURCES:
            path = root / filename
            if path.exists() and path.is_file():
                content = self._read_file(path)
                if content:
                    sections.append(f"## [{filename}]\n\n{content}")

        if not sections:
            return ""

        combined = "\n\n---\n\n".join(sections)
        logger.info(
            "ContextFileLoader: injected %d context file(s) from %s (%d chars total).",
            len(sections),
            workspace_path,
            len(combined),
        )
        return combined

    def _read_file(self, path: Path) -> str:
        """Read a file, truncating at _max_chars with a warning if needed."""
        try:
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if len(text) > self._max_chars:
                logger.warning(
                    "ContextFileLoader: %s exceeds %d chars — truncating.",
                    path.name,
                    self._max_chars,
                )
                text = text[: self._max_chars] + "\n\n[... truncated — file exceeds token limit ...]"
            return text
        except Exception as exc:
            logger.error("ContextFileLoader: could not read %s: %s", path, exc)
            return ""
