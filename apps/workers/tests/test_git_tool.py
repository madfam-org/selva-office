"""Tests for GitTool safety and edge cases."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from autoswarm_workers.tools.bash_tool import BashResult
from autoswarm_workers.tools.git_tool import GitTool


@pytest.fixture
def git_tool() -> GitTool:
    return GitTool()


@pytest.mark.asyncio
async def test_token_shell_escaping_single_quote(git_tool: GitTool) -> None:
    """Token with single-quote chars should be escaped in credential helper."""
    git_tool.bash = AsyncMock()
    git_tool.bash.execute = AsyncMock(
        return_value=BashResult(command="", stdout="", stderr="", return_code=0)
    )

    await git_tool.configure_credentials("/repo", "tok'en")

    call_args = git_tool.bash.execute.call_args[0][0]
    # The token should have the single quote escaped
    assert "tok'\\''en" in call_args


@pytest.mark.asyncio
async def test_token_shell_escaping_dollar(git_tool: GitTool) -> None:
    """Token with $ should pass through (only ' is escaped)."""
    git_tool.bash = AsyncMock()
    git_tool.bash.execute = AsyncMock(
        return_value=BashResult(command="", stdout="", stderr="", return_code=0)
    )

    await git_tool.configure_credentials("/repo", "tok$en")

    call_args = git_tool.bash.execute.call_args[0][0]
    assert "tok$en" in call_args


@pytest.mark.asyncio
async def test_create_pr_gh_not_installed(git_tool: GitTool) -> None:
    """create_pr returns graceful error when gh CLI is not installed."""
    git_tool.bash = AsyncMock()
    git_tool.bash.execute = AsyncMock(
        return_value=BashResult(
            command="command -v gh", stdout="", stderr="", return_code=1
        )
    )

    result = await git_tool.create_pr("/repo", "main", "Test PR", "Body text")

    assert result.return_code == 1
    assert "gh CLI is not installed" in result.stderr
    # Should have only called `command -v gh`, not `gh pr create`
    git_tool.bash.execute.assert_called_once()


@pytest.mark.asyncio
async def test_cleanup_worktree_shutil_fallback(git_tool: GitTool) -> None:
    """cleanup_worktree falls back to shutil.rmtree when git remove fails."""
    git_tool.bash = AsyncMock()
    # git worktree remove fails, then prune succeeds
    git_tool.bash.execute = AsyncMock(
        side_effect=[
            BashResult(
                command="git worktree remove", stdout="", stderr="error", return_code=1
            ),
            BashResult(
                command="git worktree prune", stdout="", stderr="", return_code=0
            ),
        ]
    )

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        wt_path = Path(tmpdir) / "test-worktree"
        wt_path.mkdir()
        (wt_path / "test.txt").write_text("hello")

        with patch("autoswarm_workers.tools.git_tool.shutil.rmtree") as mock_rmtree:
            await git_tool.cleanup_worktree(str(wt_path))
            mock_rmtree.assert_called_once_with(str(wt_path), ignore_errors=True)
