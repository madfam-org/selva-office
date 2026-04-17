"""Tests for BashTool sandbox hardening."""

from __future__ import annotations

import pytest

from selva_workers.tools.bash_tool import BashTool


@pytest.mark.asyncio
async def test_blocks_cd_dotdot():
    """BashTool blocks 'cd ..' when allowed_cwd is set."""
    tool = BashTool(allowed_cwd="/tmp")
    result = await tool.execute("cd .. && ls")
    assert result.return_code == 126
    assert "directory traversal" in result.stderr.lower() or "blocked" in result.stderr.lower()


@pytest.mark.asyncio
async def test_allows_cd_subdir(tmp_path):
    """BashTool allows cd to subdirectory."""
    sub = tmp_path / "subdir"
    sub.mkdir()
    tool = BashTool(allowed_cwd=str(tmp_path))
    result = await tool.execute(f"cd {sub} && pwd")
    assert result.success


@pytest.mark.asyncio
async def test_no_block_cd_dotdot_without_cwd():
    """BashTool does not block cd .. when no allowed_cwd is set."""
    tool = BashTool()
    result = await tool.execute("cd /tmp && cd .. && echo ok")
    # Without allowed_cwd, this should execute (no sandbox)
    assert result.success
    assert "ok" in result.stdout


@pytest.mark.asyncio
async def test_env_param_does_not_leak():
    """Environment variables passed via env= do not persist."""
    import os
    tool = BashTool()
    result = await tool.execute("echo $SECRET_VAR", env={"SECRET_VAR": "s3cret"})
    assert "s3cret" in result.stdout
    assert os.environ.get("SECRET_VAR") is None
