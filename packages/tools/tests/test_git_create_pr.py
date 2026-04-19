"""Tests for GitCreatePRTool."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _mock_run(queue):
    async def _call(self, command, *, timeout=30.0, cwd=None):
        if queue:
            return queue.pop(0)
        return {"stdout": "", "stderr": "", "return_code": 0, "success": True}

    return _call


class TestGitCreatePR:
    def test_schema_requires_title(self) -> None:
        from selva_tools.builtins.git import GitCreatePRTool

        schema = GitCreatePRTool().parameters_schema()
        assert schema["required"] == ["title"]

    @pytest.mark.asyncio
    async def test_refuses_from_main(self, tmp_path: Path) -> None:
        from selva_tools.builtins.git import GitCreatePRTool

        run = _mock_run([
            {"stdout": "main\n", "stderr": "", "return_code": 0, "success": True},
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await GitCreatePRTool().execute(
                title="feat: x", repo_path=str(tmp_path)
            )

        assert not result.success
        assert "protected branch" in (result.error or "")
        assert result.data["current_branch"] == "main"

    @pytest.mark.asyncio
    async def test_warns_on_non_conventional_title(self, tmp_path: Path) -> None:
        from selva_tools.builtins.git import GitCreatePRTool

        run = _mock_run([
            {"stdout": "feat/x\n", "stderr": "", "return_code": 0, "success": True},  # branch
            {
                "stdout": "https://github.com/owner/repo/pull/42\n",
                "stderr": "",
                "return_code": 0,
                "success": True,
            },
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await GitCreatePRTool().execute(
                title="added a thing", body="b", repo_path=str(tmp_path)
            )

        assert result.success
        warnings = result.data["warnings"]
        assert any("conventional" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_accepts_conventional_title(self, tmp_path: Path) -> None:
        from selva_tools.builtins.git import GitCreatePRTool

        run = _mock_run([
            {"stdout": "feat/x\n", "stderr": "", "return_code": 0, "success": True},
            {
                "stdout": "https://github.com/owner/repo/pull/7\n",
                "stderr": "",
                "return_code": 0,
                "success": True,
            },
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await GitCreatePRTool().execute(
                title="fix(auth): handle expired token", body="b", repo_path=str(tmp_path)
            )

        assert result.success
        # No conventional warning when title matches.
        assert not any("conventional" in w for w in result.data["warnings"])
        assert result.data["url"].endswith("/pull/7")

    @pytest.mark.asyncio
    async def test_loads_pr_template_when_body_empty(self, tmp_path: Path) -> None:
        from selva_tools.builtins.git import GitCreatePRTool

        template = tmp_path / ".github" / "pull_request_template.md"
        template.parent.mkdir()
        template.write_text("## Summary\n\n## Test plan\n")

        run = _mock_run([
            {"stdout": "feat/x\n", "stderr": "", "return_code": 0, "success": True},
            {
                "stdout": "https://github.com/owner/repo/pull/1\n",
                "stderr": "",
                "return_code": 0,
                "success": True,
            },
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await GitCreatePRTool().execute(
                title="feat: x", body="", repo_path=str(tmp_path)
            )

        warnings = result.data["warnings"]
        assert any("template" in w for w in warnings)

    @pytest.mark.asyncio
    async def test_merges_codeowners_with_explicit_reviewers(self, tmp_path: Path) -> None:
        from selva_tools.builtins.git import GitCreatePRTool

        codeowners = tmp_path / ".github" / "CODEOWNERS"
        codeowners.parent.mkdir()
        codeowners.write_text("* @alice @bob\n/infra/ @ops-team\n")

        run = _mock_run([
            {"stdout": "feat/x\n", "stderr": "", "return_code": 0, "success": True},
            {
                "stdout": "https://github.com/owner/repo/pull/1\n",
                "stderr": "",
                "return_code": 0,
                "success": True,
            },
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await GitCreatePRTool().execute(
                title="feat: x",
                body="b",
                repo_path=str(tmp_path),
                reviewers=["carol"],
            )

        reviewers = set(result.data["reviewers"])
        assert {"alice", "bob", "ops-team", "carol"}.issubset(reviewers)

    @pytest.mark.asyncio
    async def test_surfaces_gh_failure(self, tmp_path: Path) -> None:
        from selva_tools.builtins.git import GitCreatePRTool

        run = _mock_run([
            {"stdout": "feat/x\n", "stderr": "", "return_code": 0, "success": True},
            {
                "stdout": "",
                "stderr": "gh: not authenticated",
                "return_code": 1,
                "success": False,
            },
        ])
        with patch("selva_tools.sandbox.ToolSandbox.run_command", new=run):
            result = await GitCreatePRTool().execute(
                title="feat: x", body="b", repo_path=str(tmp_path)
            )

        assert not result.success
        assert "not authenticated" in (result.error or "")
