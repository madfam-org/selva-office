"""Tests for git credential isolation (no os.environ pollution)."""

from __future__ import annotations

import os

import pytest

from selva_workers.tools.bash_tool import BashResult, BashTool
from selva_workers.tools.git_tool import GitTool


@pytest.mark.asyncio
async def test_bash_execute_with_custom_env():
    """BashTool.execute() merges custom env without polluting os.environ."""
    tool = BashTool(timeout_seconds=5)
    result = await tool.execute("echo $MY_TEST_VAR", env={"MY_TEST_VAR": "hello123"})
    assert result.success
    assert "hello123" in result.stdout
    assert "MY_TEST_VAR" not in os.environ


@pytest.mark.asyncio
async def test_bash_execute_without_custom_env():
    """BashTool.execute() works normally without env kwarg."""
    tool = BashTool(timeout_seconds=5)
    result = await tool.execute("echo ok")
    assert result.success
    assert "ok" in result.stdout


@pytest.mark.asyncio
async def test_create_pr_passes_token_via_env():
    """GitTool.create_pr() passes GH_TOKEN via subprocess env, not os.environ."""
    git_tool = GitTool()

    captured_env = {}

    async def mock_execute(command, *, env=None):
        if "gh pr create" in command:
            captured_env.update(env or {})
        return BashResult(command=command, stdout="", stderr="", return_code=0)

    git_tool.bash.execute = mock_execute

    await git_tool.create_pr(
        "/tmp/repo", "feature/test", "Test PR", "Test body",
        token="ghp_test_token_123",
    )

    assert captured_env.get("GH_TOKEN") == "ghp_test_token_123"
    assert os.environ.get("GH_TOKEN") != "ghp_test_token_123"


@pytest.mark.asyncio
async def test_create_pr_without_token():
    """GitTool.create_pr() works without a token (env=None)."""
    git_tool = GitTool()

    captured_env = {"sentinel": True}

    async def mock_execute(command, *, env=None):
        if "gh pr create" in command:
            captured_env.clear()
            if env:
                captured_env.update(env)
        return BashResult(command=command, stdout="", stderr="", return_code=0)

    git_tool.bash.execute = mock_execute

    await git_tool.create_pr(
        "/tmp/repo", "feature/test", "Test PR", "Test body",
    )

    # No GH_TOKEN should be in env
    assert "GH_TOKEN" not in captured_env
