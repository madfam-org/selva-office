"""Developer-quality tools: lint + typecheck wrappers, diff-coverage analysis.

These tools wrap the commands that the `coding` and `pre-pr-audit` skills
otherwise have to build by hand via `bash_execute`. They:

- auto-detect project language(s) from config-file presence
- return structured findings instead of raw stdout blobs, so an LLM
  doesn't have to parse human-facing linter output
- degrade gracefully when a toolchain isn't installed (skipped, not
  errored) so a Python-only repo can run this tool without failing on
  a missing `pnpm`.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any, Literal

from ..base import BaseTool, ToolResult
from ..sandbox import ToolSandbox

# ---------- shared helpers ----------


def _detect_languages(repo: Path, explicit: list[str] | None) -> list[str]:
    """Return ["python"], ["typescript"], or both — based on config presence."""
    if explicit:
        return [lang.lower() for lang in explicit if lang.lower() in {"python", "typescript"}]
    langs: list[str] = []
    if (repo / "pyproject.toml").is_file() or next(repo.glob("*.py"), None) is not None:
        langs.append("python")
    if (repo / "package.json").is_file() and (repo / "tsconfig.json").is_file():
        langs.append("typescript")
    if not langs:
        # Fall back to python — produces a coherent "no findings" result
        # rather than erroring on a repo we can't classify.
        langs.append("python")
    return langs


async def _run(cmd: str, cwd: str, timeout: float) -> dict[str, Any]:
    sandbox = ToolSandbox()
    return await sandbox.run_command(cmd, cwd=cwd, timeout=timeout)


def _available(cwd: str, executable: str) -> bool:
    """Sync `which` — avoids launching the actual slow toolchain just to probe."""
    import shutil

    return shutil.which(executable, path=f"{cwd}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin") is not None or shutil.which(executable) is not None


# ---------- LintAndTypeCheckTool ----------


class LintAndTypeCheckTool(BaseTool):
    """Run ruff + mypy (Python) and/or eslint + tsc (TypeScript).

    Every tool is optional — if it isn't installed, we mark it skipped
    and move on. A Python-only repo without `pnpm` gets a clean result,
    not a spurious error.

    Output layout (via `ToolResult.data`):
      {
        "findings": [
          {"tool": "ruff", "severity": "error", "file": "x.py",
           "line": 12, "column": 5, "code": "F401", "message": "..."}
        ],
        "skipped": [{"tool": "mypy", "reason": "not configured"}],
        "summary": {"total": 3, "errors": 2, "warnings": 1,
                    "by_tool": {"ruff": 1, "tsc": 2}}
      }
    """

    name = "lint_and_typecheck"
    description = "Run ruff + mypy + eslint + tsc on a path. Auto-detects language; skips missing toolchains; returns structured findings."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files/dirs to check. Defaults to the repo root.",
                    "default": ["."],
                },
                "languages": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["python", "typescript"]},
                    "description": "Restrict to specific languages. Empty = auto-detect.",
                    "default": [],
                },
                "repo_path": {"type": "string", "default": "."},
                "fix": {
                    "type": "boolean",
                    "description": "Apply ruff --fix and eslint --fix for auto-fixable issues.",
                    "default": False,
                },
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        paths: list[str] = kwargs.get("paths") or ["."]
        languages: list[str] = kwargs.get("languages") or []
        repo_path: str = kwargs.get("repo_path", ".")
        fix: bool = bool(kwargs.get("fix", False))

        detected = _detect_languages(Path(repo_path), languages)
        path_args = " ".join(shlex.quote(p) for p in paths)

        findings: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []

        if "python" in detected:
            findings.extend(await self._run_ruff(path_args, repo_path, fix, skipped))
            findings.extend(await self._run_mypy(path_args, repo_path, skipped))

        if "typescript" in detected:
            findings.extend(await self._run_eslint(path_args, repo_path, fix, skipped))
            findings.extend(await self._run_tsc(repo_path, skipped))

        errors = sum(1 for f in findings if f.get("severity") == "error")
        warnings = sum(1 for f in findings if f.get("severity") == "warning")
        by_tool: dict[str, int] = {}
        for f in findings:
            by_tool[f["tool"]] = by_tool.get(f["tool"], 0) + 1

        return ToolResult(
            success=errors == 0,
            output=(
                f"{len(findings)} finding(s) — "
                f"{errors} error, {warnings} warning. "
                f"Languages: {', '.join(detected)}"
            ),
            data={
                "findings": findings,
                "skipped": skipped,
                "summary": {
                    "total": len(findings),
                    "errors": errors,
                    "warnings": warnings,
                    "by_tool": by_tool,
                    "languages": detected,
                },
            },
        )

    async def _run_ruff(
        self,
        path_args: str,
        cwd: str,
        fix: bool,
        skipped: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not _available(cwd, "ruff"):
            skipped.append({"tool": "ruff", "reason": "not installed"})
            return []
        cmd = f"ruff check {path_args} --output-format=json"
        if fix:
            cmd += " --fix"
        result = await _run(cmd, cwd=cwd, timeout=120.0)
        stdout = result["stdout"].strip()
        if not stdout:
            return []
        try:
            entries = json.loads(stdout)
        except json.JSONDecodeError:
            return [{
                "tool": "ruff",
                "severity": "error",
                "file": "",
                "line": 0,
                "column": 0,
                "code": "",
                "message": f"ruff produced non-JSON output: {stdout[:200]}",
            }]
        findings: list[dict[str, Any]] = []
        for item in entries:
            loc = item.get("location") or {}
            findings.append({
                "tool": "ruff",
                "severity": "error",
                "file": item.get("filename", ""),
                "line": loc.get("row", 0),
                "column": loc.get("column", 0),
                "code": item.get("code", ""),
                "message": item.get("message", ""),
            })
        return findings

    async def _run_mypy(
        self,
        path_args: str,
        cwd: str,
        skipped: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not _available(cwd, "mypy"):
            skipped.append({"tool": "mypy", "reason": "not installed"})
            return []
        cmd = f"mypy {path_args} --no-color-output --no-error-summary"
        result = await _run(cmd, cwd=cwd, timeout=180.0)
        findings: list[dict[str, Any]] = []
        # mypy line shape: path/to/file.py:12:5: error: message [code]
        pattern = re.compile(
            r"^(?P<file>[^:\n]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s+"
            r"(?P<sev>error|warning|note):\s+(?P<msg>.*?)(?:\s+\[(?P<code>[^\]]+)\])?$"
        )
        for raw in result["stdout"].splitlines():
            m = pattern.match(raw)
            if not m:
                continue
            if m.group("sev") == "note":
                continue  # notes attach to a preceding error; skip standalone lines
            findings.append({
                "tool": "mypy",
                "severity": "error" if m.group("sev") == "error" else "warning",
                "file": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col") or 0),
                "code": m.group("code") or "",
                "message": m.group("msg"),
            })
        return findings

    async def _run_eslint(
        self,
        path_args: str,
        cwd: str,
        fix: bool,
        skipped: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not (Path(cwd) / "node_modules" / ".bin" / "eslint").exists():
            skipped.append({"tool": "eslint", "reason": "node_modules/.bin/eslint not found"})
            return []
        cmd = f"./node_modules/.bin/eslint {path_args} --format json"
        if fix:
            cmd += " --fix"
        result = await _run(cmd, cwd=cwd, timeout=120.0)
        stdout = result["stdout"].strip()
        if not stdout:
            return []
        try:
            reports = json.loads(stdout)
        except json.JSONDecodeError:
            return [{
                "tool": "eslint",
                "severity": "error",
                "file": "",
                "line": 0,
                "column": 0,
                "code": "",
                "message": f"eslint produced non-JSON output: {stdout[:200]}",
            }]
        findings: list[dict[str, Any]] = []
        for rep in reports:
            for msg in rep.get("messages", []):
                findings.append({
                    "tool": "eslint",
                    "severity": "error" if msg.get("severity", 2) >= 2 else "warning",
                    "file": rep.get("filePath", ""),
                    "line": msg.get("line", 0),
                    "column": msg.get("column", 0),
                    "code": msg.get("ruleId", "") or "",
                    "message": msg.get("message", ""),
                })
        return findings

    async def _run_tsc(
        self,
        cwd: str,
        skipped: list[dict[str, str]],
    ) -> list[dict[str, Any]]:
        if not (Path(cwd) / "node_modules" / ".bin" / "tsc").exists():
            skipped.append({"tool": "tsc", "reason": "node_modules/.bin/tsc not found"})
            return []
        result = await _run("./node_modules/.bin/tsc --noEmit --pretty false", cwd=cwd, timeout=180.0)
        # tsc line shape: path/to/file.ts(12,5): error TS2304: Cannot find name 'foo'.
        pattern = re.compile(
            r"^(?P<file>[^(]+)\((?P<line>\d+),(?P<col>\d+)\):\s+"
            r"(?P<sev>error|warning)\s+(?P<code>TS\d+):\s+(?P<msg>.+)$"
        )
        findings: list[dict[str, Any]] = []
        for raw in result["stdout"].splitlines():
            m = pattern.match(raw)
            if not m:
                continue
            findings.append({
                "tool": "tsc",
                "severity": m.group("sev"),
                "file": m.group("file"),
                "line": int(m.group("line")),
                "column": int(m.group("col")),
                "code": m.group("code"),
                "message": m.group("msg"),
            })
        return findings


# ---------- TestCoverageForDiffTool ----------


class TestCoverageForDiffTool(BaseTool):
    """Report uncovered lines within the git diff vs a base ref.

    Runs `pytest --cov --cov-report=json` (or uses an existing
    `coverage.json`), intersects covered-line data with the lines added
    or modified in the diff, and returns a list of uncovered changed
    lines per file. Intended for the `pre-pr-audit` skill.

    Output (via ``ToolResult.data``):
      {
        "base_ref": "main",
        "changed_files": [...],
        "uncovered": [{"file": "a.py", "lines": [12, 13, 19]}],
        "summary": {"files_changed": 4, "changed_lines_total": 87,
                    "changed_lines_uncovered": 9}
      }
    """

    name = "test_coverage_for_diff"
    description = "Run coverage and report uncovered lines limited to the git diff. Graceful skip when coverage tooling is absent."

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "base_ref": {
                    "type": "string",
                    "description": "Git ref to diff against. Commonly 'main' or 'origin/main'.",
                    "default": "main",
                },
                "test_command": {
                    "type": "string",
                    "description": (
                        "Override the command that produces coverage.json. "
                        "Default: 'pytest --cov=. --cov-report=json:.coverage.json -q'."
                    ),
                    "default": "",
                },
                "coverage_file": {
                    "type": "string",
                    "description": "Path to an existing coverage.json; skips running tests if present.",
                    "default": "",
                },
                "repo_path": {"type": "string", "default": "."},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        base_ref: str = kwargs.get("base_ref", "main")
        test_command: str = kwargs.get("test_command", "") or ""
        coverage_file: str = kwargs.get("coverage_file", "") or ""
        repo_path: str = kwargs.get("repo_path", ".")

        # 1. Resolve changed files + line ranges.
        diff = await self._changed_line_ranges(base_ref, repo_path)
        if not diff:
            return ToolResult(
                output="no changes vs base ref — nothing to cover",
                data={
                    "base_ref": base_ref,
                    "changed_files": [],
                    "uncovered": [],
                    "summary": {
                        "files_changed": 0,
                        "changed_lines_total": 0,
                        "changed_lines_uncovered": 0,
                    },
                },
            )

        # 2. Obtain coverage data.
        cov_path = Path(coverage_file) if coverage_file else Path(repo_path) / ".coverage.json"
        if not cov_path.exists():
            if not _available(repo_path, "pytest"):
                return ToolResult(
                    success=False,
                    error="coverage.json missing and pytest not installed; pass coverage_file or install pytest+pytest-cov",
                    data={"base_ref": base_ref, "changed_files": list(diff.keys())},
                )
            cmd = test_command or f"pytest --cov=. --cov-report=json:{cov_path.name} -q"
            result = await _run(cmd, cwd=repo_path, timeout=600.0)
            if not cov_path.exists():
                return ToolResult(
                    success=False,
                    error=(
                        "coverage run did not produce a coverage.json. "
                        f"exit={result['return_code']} stderr={result['stderr'][:200]}"
                    ),
                )

        try:
            cov_data = json.loads(cov_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            return ToolResult(success=False, error=f"could not read coverage.json: {exc}")

        # 3. Intersect changed lines with uncovered lines.
        files_cov = cov_data.get("files", {})
        uncovered_per_file: dict[str, list[int]] = {}
        total_changed = 0
        total_uncov = 0

        for rel_path, changed_lines in diff.items():
            total_changed += len(changed_lines)
            # coverage.py sometimes keys by "./path" — normalize both sides.
            entry = (
                files_cov.get(rel_path)
                or files_cov.get(f"./{rel_path}")
                or files_cov.get(str(Path(repo_path) / rel_path))
            )
            if entry is None:
                uncovered_per_file[rel_path] = sorted(changed_lines)
                total_uncov += len(changed_lines)
                continue
            missing = set(entry.get("missing_lines", []))
            uncov = sorted(changed_lines & missing)
            if uncov:
                uncovered_per_file[rel_path] = uncov
                total_uncov += len(uncov)

        return ToolResult(
            success=total_uncov == 0,
            output=(
                f"{total_uncov} uncovered changed line(s) across "
                f"{len(uncovered_per_file)} file(s) (of {len(diff)} changed)"
            ),
            data={
                "base_ref": base_ref,
                "changed_files": sorted(diff.keys()),
                "uncovered": [
                    {"file": f, "lines": lines} for f, lines in sorted(uncovered_per_file.items())
                ],
                "summary": {
                    "files_changed": len(diff),
                    "changed_lines_total": total_changed,
                    "changed_lines_uncovered": total_uncov,
                },
            },
        )

    async def _changed_line_ranges(
        self, base_ref: str, repo_path: str
    ) -> dict[str, set[int]]:
        """Return {relpath: {added/modified line numbers}} for files of interest."""
        # `-U0` disables context lines so we only see actual @@ headers + additions.
        cmd = f"git -C {shlex.quote(repo_path)} diff -U0 {shlex.quote(base_ref)}...HEAD"
        result = await _run(cmd, cwd=repo_path, timeout=30.0)
        if not result["success"]:
            return {}
        return _parse_unified_diff_added_lines(result["stdout"])


_DIFF_FILE = re.compile(r"^\+\+\+ b/(?P<path>.+)$")
_DIFF_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<len>\d+))? @@")


def _parse_unified_diff_added_lines(diff_text: str) -> dict[str, set[int]]:
    """Extract added/modified line numbers per file from unified diff output."""
    per_file: dict[str, set[int]] = {}
    current: str | None = None
    cursor = 0
    for raw in diff_text.splitlines():
        file_match = _DIFF_FILE.match(raw)
        if file_match:
            path = file_match.group("path")
            if path == "/dev/null":
                current = None
                continue
            # Only track Python / TS / JS source files for now — coverage tooling
            # doesn't apply elsewhere.
            if not path.endswith((".py", ".ts", ".tsx", ".js", ".jsx")):
                current = None
                continue
            current = path
            per_file.setdefault(current, set())
            continue
        if current is None:
            continue
        hunk = _DIFF_HUNK.match(raw)
        if hunk:
            cursor = int(hunk.group("start"))
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            per_file[current].add(cursor)
            cursor += 1
        elif raw.startswith(" "):
            cursor += 1
        # '-' lines don't advance the +cursor
    # Drop files with no added lines (pure deletions don't need coverage).
    return {f: lines for f, lines in per_file.items() if lines}
