"""Impeccable on UI/UX tasks: skill loading, detector gate, findings loop.

MADFAM's standing rule is that impeccable (pbakaus/impeccable) is used for
any and all UI/UX work. In a worker that means:

1. **Before the graph runs** -- :func:`ui_task_fields` decides whether the task
   is UI/UX (``selva_skills.impeccable.is_ui_ux_task``) and loads the verbatim
   reference of the command the payload names (``impeccable_command``); the
   worker then adds the ``impeccable`` skill to the agent's skills.
2. **After the tests pass** -- the coding graph's ``ui_audit`` node
   (:func:`run_ui_audit`) runs the pinned detector (``impeccable_detect``) on
   the UI files the task changed. Changed UI files make a task UI/UX even when
   the description did not, and load the skill for the remaining iterations.
3. **Findings flow back** -- primary findings route once more through
   ``implement`` with :func:`feedback_section` in its prompt.
4. **Review reports the rest** -- :func:`review_section` asks the reviewer for
   a justification per remaining primary finding; :func:`finalize_after_review`
   records which are justified. The summary rides on the push-gate approval
   context and on the task result.

Enforcement (``SELVA_IMPECCABLE_ENFORCEMENT``): ``warn`` (default) never
blocks -- remaining findings, missing justifications and an unavailable
detector are reported to the human at the push gate and in the task result.
``block`` ends the graph as ``blocked`` instead of reaching the push gate when
a primary finding is unjustified or the detector could not run.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import AIMessage

from selva_skills.impeccable import (
    IMPECCABLE_SKILL_NAME,
    command_reference,
    is_ui_ux_task,
    requested_command,
    ui_files,
    with_impeccable_skill,
)

logger = logging.getLogger(__name__)

ENFORCEMENT_ENV = "SELVA_IMPECCABLE_ENFORCEMENT"
#: Detector-driven extra implement rounds before review takes over.
MAX_UI_FIX_ROUNDS = 1
#: The coding graph's overall implement cap (mirrors ``_route_after_test``).
MAX_ITERATIONS = 3
_PROMPT_FINDINGS = 25


def enforcement() -> str:
    value = os.environ.get(ENFORCEMENT_ENV, "warn").strip().lower()
    return "block" if value == "block" else "warn"


# -- 1. before the graph -------------------------------------------------------


def ui_task_fields(
    graph_type: str | None,
    payload: dict[str, Any] | None,
    description: str | None,
) -> dict[str, Any]:
    """Return the impeccable state fields of a task.

    ``ui_ux_task`` (whether the impeccable skill must be loaded),
    ``impeccable_command`` and ``impeccable_reference`` (the verbatim command
    reference, or ``""``). An unknown ``impeccable_command`` raises
    ``ValueError``.
    """
    command = requested_command(payload)
    return {
        "ui_ux_task": is_ui_ux_task(graph_type, payload, description),
        "impeccable_command": command or "",
        "impeccable_reference": command_reference(command) if command else "",
    }


# -- 2. the ui_audit node --------------------------------------------------------


def changed_ui_files(state: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for change in state.get("code_changes") or []:
        paths.extend(change.get("files_modified") or [])
    return ui_files(paths)


def _load_skill_prompt(state: dict[str, Any]) -> dict[str, Any]:
    """Add the impeccable skill to a task that turned out to touch UI files."""
    skill_ids = list(state.get("agent_skill_ids") or [])
    if IMPECCABLE_SKILL_NAME in skill_ids:
        return {}
    try:
        from selva_skills import SkillAudience, get_skill_registry

        audience = state.get("audience")
        section = get_skill_registry().build_system_prompt(
            [IMPECCABLE_SKILL_NAME],
            locale=state.get("locale", "en") or "en",
            audience=SkillAudience(audience) if audience else None,
        )
    except Exception:
        logger.warning("Failed to load the impeccable skill mid-task", exc_info=True)
        return {}
    prompt = state.get("agent_system_prompt") or ""
    return {
        "agent_skill_ids": with_impeccable_skill(skill_ids),
        "agent_system_prompt": f"{prompt}\n\n---\n\n{section}" if prompt else section,
    }


def _detect(worktree: str, files: list[str]) -> dict[str, Any]:
    from selva_tools.builtins.impeccable_detect import ImpeccableDetectTool

    from .graphs.base import run_async

    result = run_async(ImpeccableDetectTool().execute(repo_path=worktree, paths=files))
    return dict(result.data)


def run_ui_audit(state: dict[str, Any]) -> dict[str, Any]:
    """Body of the coding graph's ``ui_audit`` node."""
    files = changed_ui_files(state)
    if not state.get("ui_ux_task") and not files:
        return state  # not UI/UX work: nothing to do

    updates: dict[str, Any] = {"ui_ux_task": True, **_load_skill_prompt(state)}
    previous = state.get("ui_audit") or {}
    rounds = int(previous.get("rounds", 0)) + 1
    worktree = state.get("worktree_path")

    if not files:
        report: dict[str, Any] = {
            "status": "no_ui_files",
            "findings": [],
            "primary_count": 0,
            "advisory_count": 0,
            "files_scanned": [],
        }
    elif not worktree:
        report = {
            "status": "unavailable",
            "error": "no worktree to scan",
            "findings": [],
            "primary_count": 0,
            "advisory_count": 0,
            "files_scanned": [],
        }
    else:
        try:
            report = _detect(worktree, files)
        except Exception as exc:  # fail visible, never "clean"
            logger.warning("impeccable_detect failed", exc_info=True)
            report = {
                "status": "error",
                "error": str(exc),
                "findings": [],
                "primary_count": 0,
                "advisory_count": 0,
                "files_scanned": files,
            }

    audit = {**report, "rounds": rounds, "enforcement": enforcement()}
    summary = _summary_line(audit)
    message = AIMessage(
        content=summary,
        additional_kwargs={"action_category": "file_read", "ui_audit": _compact(audit)},
    )
    return {
        **state,
        **updates,
        "ui_audit": audit,
        "messages": [*state.get("messages", []), message],
        "status": "ui_audit",
    }


def route_after_ui_audit(state: dict[str, Any]) -> str:
    """Primary findings get one more implement round; then review."""
    audit = state.get("ui_audit") or {}
    if (
        audit.get("status") == "findings"
        and int(audit.get("rounds", 0)) <= MAX_UI_FIX_ROUNDS
        and int(state.get("iteration", 0)) < MAX_ITERATIONS
    ):
        return "implement"
    return "review"


# -- 3./4. prompt sections ---------------------------------------------------------


def _primary(audit: dict[str, Any]) -> list[dict[str, Any]]:
    return [f for f in audit.get("findings") or [] if not f.get("advisory")]


def _finding_line(f: dict[str, Any]) -> str:
    return (
        f"- `{f.get('rule')}` at {f.get('file')}:{f.get('line')} -- {f.get('name')}: "
        f"{f.get('snippet')}"
    )


def feedback_section(state: dict[str, Any]) -> str:
    """Implement-prompt section listing the detector findings to fix."""
    audit = state.get("ui_audit") or {}
    primary = _primary(audit)
    if audit.get("status") != "findings" or not primary:
        return ""
    lines = [
        "## Impeccable detector findings to fix in this iteration",
        "",
        "The pinned impeccable detector flagged these in the files you changed. Fix "
        "each one in place, keeping the brief and the project's design system. "
        "Leave a finding only when it is deliberate; the review will ask you to "
        "justify it.",
        "",
        *(_finding_line(f) for f in primary[:_PROMPT_FINDINGS]),
    ]
    return "\n".join(lines)


def review_section(state: dict[str, Any]) -> str:
    """Review-prompt section: report remaining findings with a justification."""
    audit = state.get("ui_audit")
    if not audit:
        return ""
    primary = _primary(audit)
    lines = ["## Impeccable UI/UX gate", "", _summary_line(audit)]
    if primary:
        lines += [
            "",
            "Remaining primary findings:",
            *(_finding_line(f) for f in primary[:_PROMPT_FINDINGS]),
            "",
            "Add the key 'ui_findings_justification' to your JSON: an array of "
            "objects with 'rule', 'file', 'line' and 'justification' (one line: the "
            "pinned brief, a mandated design-system token, or a false positive), one "
            "per finding you accept. Recommend 'revise' for any finding that is not "
            "deliberate.",
        ]
    return "\n".join(lines)


def finalize_after_review(state: dict[str, Any], review_summary: dict[str, Any]) -> dict[str, Any]:
    """Return state updates recording justified vs unjustified findings."""
    audit = state.get("ui_audit")
    if not audit:
        return {}
    raw = review_summary.get("ui_findings_justification")
    justifications = [j for j in raw if isinstance(j, dict)] if isinstance(raw, list) else []
    justified_keys = {
        (str(j.get("rule")), str(j.get("file")))
        for j in justifications
        if str(j.get("justification") or "").strip()
    }
    remaining = _primary(audit)
    unjustified = [f for f in remaining if (f.get("rule"), f.get("file")) not in justified_keys]
    final = {
        **audit,
        "remaining": remaining,
        "justifications": justifications,
        "unjustified_count": len(unjustified),
    }
    updates: dict[str, Any] = {"ui_audit": final}
    detector_ran = audit.get("status") in ("clean", "findings", "no_ui_files")
    if enforcement() == "block" and (unjustified or not detector_ran):
        reason = (
            f"{len(unjustified)} unjustified impeccable finding(s)"
            if detector_ran
            else f"impeccable detector {audit.get('status')}: {audit.get('error', '')}"
        )
        updates["status"] = "blocked"
        updates["result"] = {"error": f"UI/UX gate blocked: {reason}", "ui_audit": _compact(final)}
    return updates


def approval_summary(state: dict[str, Any]) -> dict[str, Any] | None:
    """What the push gate and the task result show about the UI/UX gate."""
    audit = state.get("ui_audit")
    return _compact(audit) if audit else None


# -- helpers -------------------------------------------------------------------------


def _summary_line(audit: dict[str, Any]) -> str:
    status = audit.get("status")
    files = len(audit.get("files_scanned") or [])
    if status in ("clean", "findings"):
        return (
            f"Impeccable detector ({audit.get('npm_version')}, engine "
            f"{audit.get('engine_version')}, telemetry off): {audit.get('primary_count', 0)} "
            f"primary, {audit.get('advisory_count', 0)} advisory finding(s) in {files} file(s)."
        )
    if status == "no_ui_files":
        return "Impeccable detector: no changed UI files to scan."
    return f"Impeccable detector {status}: deterministic scan unavailable ({audit.get('error')})."


def _compact(audit: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "status",
        "error",
        "primary_count",
        "advisory_count",
        "files_scanned",
        "engine_version",
        "npm_version",
        "telemetry",
        "rounds",
        "enforcement",
        "unjustified_count",
        "justifications",
    )
    out = {k: audit[k] for k in keep if k in audit}
    out["remaining"] = (audit.get("remaining") or _primary(audit))[:_PROMPT_FINDINGS]
    return out


def skill_context(state: dict[str, Any], stage: str) -> str:
    """The skill prompt for a coding-graph node, with impeccable additions.

    ``stage`` is ``plan``, ``implement`` or ``review``. The command reference
    rides on every stage; detector feedback on ``implement``; the gate on
    ``review``.
    """
    parts = [state.get("agent_system_prompt") or "", state.get("impeccable_reference") or ""]
    if stage == "implement":
        parts.append(feedback_section(state))
    elif stage == "review":
        parts.append(review_section(state))
    return "\n\n---\n\n".join(p for p in parts if p)
