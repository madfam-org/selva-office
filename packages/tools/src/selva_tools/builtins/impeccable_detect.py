"""``impeccable_detect`` -- the pinned impeccable UI anti-pattern detector.

MADFAM's standing rule is that impeccable (pbakaus/impeccable, Apache-2.0) is
used for any and all UI/UX work. This tool runs its deterministic detector
(``impeccable detect --json``: rule-based, no LLM, no key, no network for
local files) over the UI files a task changed, and returns structured
findings the agent loop feeds back into the next implement iteration.

Guarantees:

* **Pinned.** The engine version comes from
  ``packages/skills/vendor/impeccable.pin.json``. The binary is baked into the
  workers image by ``scripts/vendor-impeccable.py fetch-engine`` (sha512
  verified) and found through ``IMPECCABLE_BIN``. A binary that reports a
  different version is refused.
* **Telemetry off.** The child process gets a minimal environment with
  ``IMPECCABLE_NO_TELEMETRY=1`` and ``DO_NOT_TRACK=1``; nothing else from the
  worker's environment (no provider keys, no tokens) is passed through.
* **Read-only on the workspace.** Only ``detect`` is ever invoked, only on
  existing files inside ``repo_path`` (no URLs, no ``--cdp``, no absolute or
  ``..`` paths, no option-like names).
* **Fail visible.** A missing or mismatched binary is ``status="unavailable"``
  with an error, never an empty "clean" result.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult
from ..sandbox import ToolSandbox

#: Environment forced on every detector run (telemetry opt-outs upstream honours).
TELEMETRY_OFF_ENV: dict[str, str] = {
    "IMPECCABLE_NO_TELEMETRY": "1",
    "DO_NOT_TRACK": "1",
}

#: Worker variables the detector process may inherit. Everything else is dropped.
_INHERITED_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")

#: Default install location of the engine inside the workers image.
DEFAULT_BIN = "/opt/impeccable/bin/impeccable"

#: Extensions treated as UI when files are derived from git (mirrors
#: ``selva_skills.impeccable.UI_FILE_EXTENSIONS``; a test keeps them equal).
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
#: Everything the upstream detector can scan (explicit ``paths`` may use these).
SCANNABLE_EXTENSIONS: tuple[str, ...] = (*UI_FILE_EXTENSIONS, ".js", ".ts")

_SCOPES = ("type", "layout")
_MAX_FINDINGS = 200
_TIMEOUT_S = 120.0

_DEFAULT_PIN = (
    Path(__file__).resolve().parents[4] / "skills" / "vendor" / "impeccable.pin.json"
)


def load_pin() -> dict[str, Any] | None:
    """Return the vendored pin, or ``None`` when it cannot be read."""
    path = Path(os.environ.get("SELVA_IMPECCABLE_PIN") or _DEFAULT_PIN)
    try:
        pin: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return pin


def detector_env() -> dict[str, str]:
    """The complete environment of a detector run (allowlist + telemetry off)."""
    env = {k: os.environ[k] for k in _INHERITED_ENV if os.environ.get(k)}
    env.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    env.update(TELEMETRY_OFF_ENV)
    return env


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _has_ext(path: str, exts: tuple[str, ...]) -> bool:
    lower = path.lower()
    return any(lower.endswith(ext) for ext in exts)


class ImpeccableDetectTool(BaseTool):
    """Run the pinned impeccable detector on a task's changed UI files.

    ``ToolResult.data``::

        {
          "status": "clean" | "findings" | "no_ui_files" | "unavailable" | "error",
          "findings": [{"rule", "name", "severity", "category", "file",
                        "line", "snippet", "advisory", "description"}],
          "primary_count": 2, "advisory_count": 1,
          "files_scanned": ["apps/web/src/page.tsx"],
          "rejected_paths": [{"path": "...", "reason": "..."}],
          "engine_version": "0.1.16", "npm_version": "4.7.0",
          "telemetry": "off", "truncated": false
        }

    ``success`` is ``True`` only for ``clean`` and ``no_ui_files``.
    """

    name = "impeccable_detect"
    description = (
        "Run impeccable's pinned deterministic UI anti-pattern detector (read-only, "
        "telemetry off) on the task's changed UI files (.html/.css/.tsx/.jsx/.vue/"
        ".svelte/...). Defaults to files changed vs git HEAD plus untracked files. "
        "Returns structured findings; primary findings must be fixed or justified."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repo_path": {
                    "type": "string",
                    "description": "Workspace root (the task's worktree).",
                    "default": ".",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Files relative to repo_path. Empty = changed UI files from git."
                    ),
                    "default": [],
                },
                "base_ref": {
                    "type": "string",
                    "description": "Diff base for derived files (default HEAD).",
                    "default": "HEAD",
                },
                "scope": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(_SCOPES)},
                    "description": "Restrict to design domains (type, layout).",
                    "default": [],
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        repo = Path(str(kwargs.get("repo_path") or ".")).resolve()
        if not repo.is_dir():
            return self._fail("error", f"repo_path is not a directory: {repo}")
        requested = [str(p) for p in (kwargs.get("paths") or [])]
        base_ref = str(kwargs.get("base_ref") or "HEAD")
        scopes = [s for s in (kwargs.get("scope") or []) if s in _SCOPES]

        rejected: list[dict[str, str]] = []
        if requested:
            candidates, exts = requested, SCANNABLE_EXTENSIONS
        else:
            derived = await self._changed_files(repo, base_ref)
            if derived is None:
                return self._fail("error", f"could not list changed files in {repo}")
            candidates, exts = derived, UI_FILE_EXTENSIONS
        files = self._validate(repo, candidates, exts, rejected, explicit=bool(requested))
        if not files:
            return ToolResult(
                success=True,
                output="No UI files to scan.",
                data=self._data("no_ui_files", rejected=rejected),
            )

        pin = load_pin()
        if pin is None:
            return self._fail("unavailable", "impeccable pin file not found", rejected)
        argv, problem = await self._resolve_command(pin)
        if argv is None:
            return self._fail("unavailable", problem, rejected, pin)

        cmd = [*argv, "detect", "--json"]
        if scopes:
            cmd += ["--scope", ",".join(scopes)]
        cmd += files
        result = await ToolSandbox().run_command(
            cmd, cwd=str(repo), timeout=_TIMEOUT_S, env=detector_env()
        )
        code = result["return_code"]
        try:
            raw = json.loads(result["stdout"] or "[]")
        except json.JSONDecodeError:
            raw = None
        if code not in (0, 2) or not isinstance(raw, list):
            stderr = (result["stderr"] or "").strip()[:500]
            return self._fail(
                "error", f"detector exited {code}: {stderr}", rejected, pin, files
            )

        findings = [self._normalize(item, repo) for item in raw if isinstance(item, dict)]
        primary = [f for f in findings if not f["advisory"]]
        advisory = len(findings) - len(primary)
        truncated = len(findings) > _MAX_FINDINGS
        status = "findings" if primary else "clean"
        return ToolResult(
            success=not primary,
            output=(
                f"impeccable detect: {len(primary)} primary, {advisory} advisory "
                f"finding(s) in {len(files)} file(s)."
            ),
            data=self._data(
                status,
                findings=findings[:_MAX_FINDINGS],
                primary_count=len(primary),
                advisory_count=advisory,
                files_scanned=files,
                rejected=rejected,
                pin=pin,
                truncated=truncated,
            ),
        )

    # -- helpers ---------------------------------------------------------------

    async def _changed_files(self, repo: Path, base_ref: str) -> list[str] | None:
        sandbox = ToolSandbox()
        diff = await sandbox.run_command(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", base_ref, "--"],
            cwd=str(repo),
            timeout=30.0,
        )
        untracked = await sandbox.run_command(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=str(repo),
            timeout=30.0,
        )
        if not diff["success"] or not untracked["success"]:
            return None
        names = diff["stdout"].splitlines() + untracked["stdout"].splitlines()
        return [n.strip() for n in names if n.strip()]

    @staticmethod
    def _validate(
        repo: Path,
        candidates: list[str],
        exts: tuple[str, ...],
        rejected: list[dict[str, str]],
        *,
        explicit: bool,
    ) -> list[str]:
        files: dict[str, None] = {}
        for rel in candidates:
            reason = None
            if "://" in rel:
                reason = "URLs are not scanned; only workspace files"
            elif rel.startswith(("/", "-")) or ".." in Path(rel).parts:
                reason = "must be a relative path inside repo_path"
            elif not _has_ext(rel, exts):
                if not explicit:
                    continue  # derived non-UI file: not an error
                reason = "not a scannable UI file"
            else:
                target = (repo / rel).resolve()
                if not target.is_relative_to(repo):
                    reason = "resolves outside repo_path"
                elif not target.is_file():
                    reason = "file does not exist"
            if reason:
                rejected.append({"path": rel, "reason": reason})
            else:
                files.setdefault(rel, None)
        return list(files)

    async def _resolve_command(self, pin: dict[str, Any]) -> tuple[list[str] | None, str]:
        engine = str(pin.get("engine_version", ""))
        binary = os.environ.get("IMPECCABLE_BIN") or DEFAULT_BIN
        if Path(binary).is_file() and os.access(binary, os.X_OK):
            probe = await ToolSandbox().run_command(
                [binary, "--version"], timeout=15.0, env=detector_env()
            )
            reported = probe["stdout"].strip()
            if reported != f"{engine}+engine":
                return None, (
                    f"impeccable binary {binary} reports {reported or probe['stderr'][:200]!r}, "
                    f"pinned engine is {engine}"
                )
            return [binary], ""
        npx = shutil.which("npx")
        if npx and _truthy(os.environ.get("SELVA_IMPECCABLE_ALLOW_NPX")):
            return [npx, "--yes", f"impeccable@{pin['npm_version']}"], ""
        return None, (
            f"impeccable engine {engine} not installed: set IMPECCABLE_BIN or run "
            "`python3 scripts/vendor-impeccable.py fetch-engine --dest <dir>` "
            "(or SELVA_IMPECCABLE_ALLOW_NPX=1 for local development)"
        )

    @staticmethod
    def _normalize(item: dict[str, Any], repo: Path) -> dict[str, Any]:
        file = str(item.get("file", ""))
        if file:
            path = Path(file)
            path = path if path.is_absolute() else repo / path
            with contextlib.suppress(ValueError):
                file = str(path.resolve().relative_to(repo))
        advisory = bool(item.get("advisory")) or item.get("severity") == "advisory"
        return {
            "rule": str(item.get("antipattern", "")),
            "name": str(item.get("name", "")),
            "severity": str(item.get("severity", "")),
            "category": str(item.get("category", "")),
            "file": file,
            "line": int(item.get("line") or 0),
            "snippet": str(item.get("snippet", ""))[:200],
            "advisory": advisory,
            "description": str(item.get("description", ""))[:400],
        }

    @staticmethod
    def _data(
        status: str,
        *,
        findings: list[dict[str, Any]] | None = None,
        primary_count: int = 0,
        advisory_count: int = 0,
        files_scanned: list[str] | None = None,
        rejected: list[dict[str, str]] | None = None,
        pin: dict[str, Any] | None = None,
        truncated: bool = False,
        error: str | None = None,
    ) -> dict[str, Any]:
        pin = pin or load_pin() or {}
        data: dict[str, Any] = {
            "status": status,
            "findings": findings or [],
            "primary_count": primary_count,
            "advisory_count": advisory_count,
            "files_scanned": files_scanned or [],
            "rejected_paths": rejected or [],
            "engine_version": pin.get("engine_version"),
            "npm_version": pin.get("npm_version"),
            "telemetry": "off",
            "truncated": truncated,
        }
        if error:
            data["error"] = error
        return data

    def _fail(
        self,
        status: str,
        message: str,
        rejected: list[dict[str, str]] | None = None,
        pin: dict[str, Any] | None = None,
        files: list[str] | None = None,
    ) -> ToolResult:
        return ToolResult(
            success=False,
            output=f"impeccable detect {status}: {message}",
            error=message,
            data=self._data(
                status, rejected=rejected, pin=pin, files_scanned=files, error=message
            ),
        )

