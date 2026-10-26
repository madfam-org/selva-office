"""Impeccable (pbakaus/impeccable) as the UI/UX skill of every Selva UI task.

MADFAM's standing rule is that impeccable is used for any and all UI/UX work.
This module owns the two decisions the worker needs:

* **Is this task UI/UX?** -- :func:`is_ui_ux_task` (explicit payload flag or
  command first, then a conservative keyword heuristic for coding tasks) and
  :func:`ui_files` (changed files whose extension is markup, style or a UI
  component). Either one being true makes the task a UI/UX task.
* **What does the agent read?** -- :func:`with_impeccable_skill` adds the
  ``impeccable`` skill to the task's skills, and :func:`command_reference`
  returns the verbatim upstream reference for a named command
  (``audit``, ``polish``, ``critique`` ...).

The skill text is vendored verbatim under ``packages/skills/vendor/impeccable``
and pinned in ``impeccable.pin.json``; ``scripts/vendor-impeccable.py`` renders
``skill-definitions/impeccable/SKILL.md`` from it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path
from typing import Any

IMPECCABLE_SKILL_NAME = "impeccable"

VENDOR_DIR = Path(__file__).resolve().parent.parent / "vendor" / "impeccable"
PIN_PATH = VENDOR_DIR.parent / "impeccable.pin.json"

#: Graph types whose every task is UI/UX. Empty by default: no current graph
#: is UI-only. Coding tasks qualify per task (payload flag, command, keywords
#: or changed UI files). Owner decision -- see the PR body.
UI_UX_GRAPH_TYPES: frozenset[str] = frozenset()

#: Graphs that can produce UI files and therefore run the detector gate.
UI_CAPABLE_GRAPH_TYPES: frozenset[str] = frozenset({"coding"})

#: Extensions the detector scans that are unambiguously UI. Plain ``.js`` and
#: ``.ts`` are scannable upstream too but are mostly non-UI here; pass them
#: explicitly to ``impeccable_detect`` when they carry styles.
UI_FILE_EXTENSIONS: tuple[str, ...] = (
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".less",
    ".jsx",
    ".tsx",
    ".vue",
    ".svelte",
    ".astro",
    ".blade.php",
)

# Words that mark a coding task as UI/UX work. Kept narrow on purpose: a
# false positive costs one detector run plus ~5k prompt tokens, a false
# negative is still caught by the changed-file check after implement.
_UI_KEYWORDS = re.compile(
    r"\b("
    r"ui|ux|frontend|front-end|landing page|web page|webpage|page layout|"
    r"component|components|css|tailwind|stylesheet|styling|layout|typography|"
    r"responsive|accessibility|a11y|wcag|dark mode|theme|design system|"
    r"design review|redesign|mockup|wireframe|empty state|onboarding flow|"
    r"form|forms|modal|dialog|dashboard|navbar|navigation bar|button|buttons|"
    r"ux copy|microcopy|interfaz|diseño|pantalla|página|maquetación"
    r")\b",
    re.IGNORECASE,
)


@cache
def load_pin() -> dict[str, Any]:
    """Return the vendored pin (tag, commit, npm + engine versions, hashes)."""
    pin: dict[str, Any] = json.loads(PIN_PATH.read_text(encoding="utf-8"))
    return pin


@cache
def commands() -> tuple[str, ...]:
    """The upstream command names, in upstream order (24 at 4.7.0)."""
    meta = json.loads(
        (VENDOR_DIR / "scripts" / "command-metadata.json").read_text(encoding="utf-8")
    )
    return tuple(meta)


def is_ui_file(path: str) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in UI_FILE_EXTENSIONS)


def ui_files(paths: Iterable[str]) -> list[str]:
    """Return the UI files among *paths*, de-duplicated, order preserved."""
    seen: dict[str, None] = {}
    for path in paths:
        if isinstance(path, str) and path and is_ui_file(path):
            seen.setdefault(path, None)
    return list(seen)


def requested_command(payload: Mapping[str, Any] | None) -> str | None:
    """Return ``payload['impeccable_command']`` when it names an upstream command.

    Raises ``ValueError`` for an unknown command so a typo fails visibly
    instead of silently loading no reference.
    """
    if not payload:
        return None
    raw = payload.get("impeccable_command")
    if raw is None or raw == "":
        return None
    name = str(raw).strip().lower().lstrip("/")
    if name.startswith("impeccable "):
        name = name.split(" ", 1)[1].strip()
    name = name.split(" ", 1)[0]
    if name == "teach":  # upstream alias
        name = "init"
    if name not in commands():
        raise ValueError(
            f"unknown impeccable_command {raw!r}; expected one of: {', '.join(commands())}"
        )
    return name


def is_ui_ux_task(
    graph_type: str | None,
    payload: Mapping[str, Any] | None = None,
    description: str | None = None,
) -> bool:
    """Decide whether a task is UI/UX before any code is written.

    Order: an explicit ``payload['ui_ux']`` boolean wins (``False`` opts a
    task out of the heuristics); a named ``impeccable_command`` makes it UI;
    a graph in :data:`UI_UX_GRAPH_TYPES` makes it UI; otherwise a coding task
    is UI when its description uses UI vocabulary.
    """
    payload = payload or {}
    explicit = payload.get("ui_ux")
    if isinstance(explicit, bool):
        return explicit
    if payload.get("impeccable_command"):
        return True
    if graph_type in UI_UX_GRAPH_TYPES:
        return True
    if graph_type in UI_CAPABLE_GRAPH_TYPES and description:
        return _UI_KEYWORDS.search(description) is not None
    return False


def with_impeccable_skill(skill_ids: Iterable[str]) -> list[str]:
    """Return *skill_ids* with the impeccable skill appended once."""
    result = list(skill_ids)
    if IMPECCABLE_SKILL_NAME not in result:
        result.append(IMPECCABLE_SKILL_NAME)
    return result


def command_reference(command: str, *, native: bool = False) -> str:
    """Return the verbatim upstream reference for *command* as a prompt section.

    With ``native=True`` the ``<command>.native.md`` variant is used when
    upstream ships one (``audit``, ``adapt``).
    """
    if command not in commands():
        raise ValueError(f"unknown impeccable command {command!r}")
    ref_dir = VENDOR_DIR / "reference"
    path = ref_dir / f"{command}.native.md" if native else ref_dir / f"{command}.md"
    if native and not path.is_file():
        path = ref_dir / f"{command}.md"
    body = path.read_text(encoding="utf-8").strip()
    version = load_pin()["npm_version"]
    return (
        f"## Skill reference: impeccable `{command}` "
        f"(upstream {version}, reference/{path.name}, verbatim)\n\n{body}"
    )
