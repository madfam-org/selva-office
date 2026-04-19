"""Tests for LintAndTypeCheckTool and TestCoverageForDiffTool."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest


# ---------- helpers ----------


def _mock_run(returns):
    """Build a sandbox.run_command stub.

    ``returns`` is a list of dicts; each run_command call pops the next.
    """
    calls = []
    queue = list(returns)

    async def _call(self, command, *, timeout=30.0, cwd=None):
        calls.append({"command": command, "timeout": timeout, "cwd": cwd})
        if queue:
            return queue.pop(0)
        return {"stdout": "", "stderr": "", "return_code": 0, "success": True}

    return _call, calls


# ---------- LintAndTypeCheckTool ----------


class TestLintAndTypeCheck:
    def test_schema_has_paths_and_languages(self) -> None:
        from selva_tools.builtins.dev_quality import LintAndTypeCheckTool

        schema = LintAndTypeCheckTool().parameters_schema()
        assert "paths" in schema["properties"]
        assert "languages" in schema["properties"]
        assert "fix" in schema["properties"]

    @pytest.mark.asyncio
    async def test_autodetects_python_from_pyproject(self, tmp_path: Path) -> None:
        from selva_tools.builtins import dev_quality as dq

        (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
        (tmp_path / "x.py").write_text("x = 1\n")

        run, _calls = _mock_run([
            {"stdout": "[]", "stderr": "", "return_code": 0, "success": True},  # ruff
        ])

        with (
            patch("selva_tools.sandbox.ToolSandbox.run_command", new=run),
            patch.object(dq, "_available", side_effect=lambda cwd, exe: exe == "ruff"),
        ):
            tool = dq.LintAndTypeCheckTool()
            result = await tool.execute(repo_path=str(tmp_path))

        assert result.success
        assert "python" in result.data["summary"]["languages"]
        skipped_tools = {s["tool"] for s in result.data["skipped"]}
        assert "mypy" in skipped_tools  # mypy unavailable → skipped, not errored

    @pytest.mark.asyncio
    async def test_parses_ruff_json_into_structured_findings(self, tmp_path: Path) -> None:
        from selva_tools.builtins import dev_quality as dq

        (tmp_path / "pyproject.toml").write_text("")
        ruff_payload = json.dumps([
            {
                "code": "F401",
                "filename": "x.py",
                "location": {"row": 12, "column": 5},
                "message": "imported but unused",
            },
        ])
        run, _calls = _mock_run([
            {"stdout": ruff_payload, "stderr": "", "return_code": 1, "success": False},
        ])

        with (
            patch("selva_tools.sandbox.ToolSandbox.run_command", new=run),
            patch.object(dq, "_available", side_effect=lambda cwd, exe: exe == "ruff"),
        ):
            result = await dq.LintAndTypeCheckTool().execute(repo_path=str(tmp_path))

        assert not result.success  # errors → success=False
        findings = result.data["findings"]
        assert len(findings) == 1
        assert findings[0]["code"] == "F401"
        assert findings[0]["line"] == 12
        assert findings[0]["severity"] == "error"
        assert result.data["summary"]["errors"] == 1

    @pytest.mark.asyncio
    async def test_parses_mypy_error_lines(self, tmp_path: Path) -> None:
        from selva_tools.builtins import dev_quality as dq

        (tmp_path / "pyproject.toml").write_text("")
        mypy_out = (
            "services/foo.py:42:5: error: Incompatible return value [return-value]\n"
            "services/foo.py:42:5: note: Expected str\n"  # note — ignored
            "services/bar.py:7: warning: Unused import [unused-import]\n"
        )
        run, _calls = _mock_run([
            {"stdout": "[]", "stderr": "", "return_code": 0, "success": True},  # ruff
            {"stdout": mypy_out, "stderr": "", "return_code": 1, "success": False},  # mypy
        ])

        with (
            patch("selva_tools.sandbox.ToolSandbox.run_command", new=run),
            patch.object(dq, "_available", return_value=True),
        ):
            result = await dq.LintAndTypeCheckTool().execute(repo_path=str(tmp_path))

        findings = [f for f in result.data["findings"] if f["tool"] == "mypy"]
        assert len(findings) == 2
        assert findings[0]["code"] == "return-value"
        assert findings[0]["line"] == 42
        assert findings[1]["severity"] == "warning"

    @pytest.mark.asyncio
    async def test_skips_gracefully_when_no_toolchain_installed(self, tmp_path: Path) -> None:
        from selva_tools.builtins import dev_quality as dq

        (tmp_path / "pyproject.toml").write_text("")

        run, _calls = _mock_run([])

        with (
            patch("selva_tools.sandbox.ToolSandbox.run_command", new=run),
            patch.object(dq, "_available", return_value=False),
        ):
            result = await dq.LintAndTypeCheckTool().execute(repo_path=str(tmp_path))

        # No findings + no error — just skipped entries.
        assert result.success
        assert result.data["findings"] == []
        skipped = {s["tool"] for s in result.data["skipped"]}
        assert {"ruff", "mypy"}.issubset(skipped)


# ---------- TestCoverageForDiffTool ----------


class TestTestCoverageForDiff:
    def test_schema_has_base_ref(self) -> None:
        from selva_tools.builtins.dev_quality import TestCoverageForDiffTool

        schema = TestCoverageForDiffTool().parameters_schema()
        assert schema["properties"]["base_ref"]["default"] == "main"

    def test_parses_unified_diff_added_lines(self) -> None:
        from selva_tools.builtins.dev_quality import _parse_unified_diff_added_lines

        diff = (
            "diff --git a/x.py b/x.py\n"
            "--- a/x.py\n"
            "+++ b/x.py\n"
            "@@ -10,0 +11,2 @@\n"
            "+line_a = 1\n"
            "+line_b = 2\n"
            "@@ -20,1 +22,1 @@\n"
            "-old\n"
            "+new\n"
            "diff --git a/README.md b/README.md\n"
            "--- a/README.md\n"
            "+++ b/README.md\n"
            "@@ -1,0 +2,1 @@\n"
            "+not code\n"
        )
        result = _parse_unified_diff_added_lines(diff)
        assert result == {"x.py": {11, 12, 22}}  # README.md filtered out
        # Pure deletion file not present.

    @pytest.mark.asyncio
    async def test_no_changed_files_returns_empty(self, tmp_path: Path) -> None:
        from selva_tools.builtins import dev_quality as dq

        run, _calls = _mock_run([
            {"stdout": "", "stderr": "", "return_code": 0, "success": True},  # git diff empty
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await dq.TestCoverageForDiffTool().execute(
                base_ref="main", repo_path=str(tmp_path)
            )
        assert result.success
        assert result.data["summary"]["files_changed"] == 0

    @pytest.mark.asyncio
    async def test_reports_uncovered_changed_lines(self, tmp_path: Path) -> None:
        from selva_tools.builtins import dev_quality as dq

        diff_out = (
            "--- a/a.py\n"
            "+++ b/a.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+one\n"
            "+two\n"
            "+three\n"
        )
        cov_path = tmp_path / ".coverage.json"
        cov_path.write_text(json.dumps({
            "files": {
                "a.py": {"missing_lines": [2, 3]},
            },
        }))

        run, _calls = _mock_run([
            {"stdout": diff_out, "stderr": "", "return_code": 0, "success": True},
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await dq.TestCoverageForDiffTool().execute(
                base_ref="main",
                coverage_file=str(cov_path),
                repo_path=str(tmp_path),
            )

        # lines 1,2,3 changed; 2,3 uncovered.
        assert not result.success
        uncov = result.data["uncovered"]
        assert uncov == [{"file": "a.py", "lines": [2, 3]}]
        assert result.data["summary"] == {
            "files_changed": 1,
            "changed_lines_total": 3,
            "changed_lines_uncovered": 2,
        }

    @pytest.mark.asyncio
    async def test_file_not_in_coverage_marks_all_lines_uncovered(
        self, tmp_path: Path
    ) -> None:
        from selva_tools.builtins import dev_quality as dq

        diff_out = (
            "--- a/new_module.py\n"
            "+++ b/new_module.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def foo(): pass\n"
            "+def bar(): pass\n"
        )
        cov_path = tmp_path / ".coverage.json"
        cov_path.write_text(json.dumps({"files": {}}))

        run, _calls = _mock_run([
            {"stdout": diff_out, "stderr": "", "return_code": 0, "success": True},
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await dq.TestCoverageForDiffTool().execute(
                base_ref="main",
                coverage_file=str(cov_path),
                repo_path=str(tmp_path),
            )

        assert result.data["uncovered"] == [{"file": "new_module.py", "lines": [1, 2]}]
