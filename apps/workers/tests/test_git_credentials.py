"""Tests for Git credential configuration (Gap A)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest


class TestConfigureCredentials:
    """GitTool.configure_credentials sets repo-local credential helper."""

    @pytest.mark.asyncio
    async def test_sets_credential_helper(self) -> None:
        from selva_workers.tools.git_tool import GitTool

        tool = GitTool()
        tool.bash = MagicMock()
        tool.bash.execute = AsyncMock(
            return_value=MagicMock(success=True, stdout="", stderr="", return_code=0)
        )

        await tool.configure_credentials("/repo", "ghp_test123")

        tool.bash.execute.assert_called_once()
        cmd = tool.bash.execute.call_args[0][0]
        assert "credential.helper" in cmd
        assert "ghp_test123" in cmd
        assert "--local" in cmd

    @pytest.mark.asyncio
    async def test_helper_targets_github(self) -> None:
        from selva_workers.tools.git_tool import GitTool

        tool = GitTool()
        tool.bash = MagicMock()
        tool.bash.execute = AsyncMock(
            return_value=MagicMock(success=True, stdout="", stderr="", return_code=0)
        )

        await tool.configure_credentials("/repo", "ghp_abc")

        cmd = tool.bash.execute.call_args[0][0]
        assert "github.com" in cmd
        assert "x-access-token" in cmd


class TestPushWithToken:
    """GitTool.push calls configure_credentials when token is provided."""

    @pytest.mark.asyncio
    async def test_push_with_token_configures_credentials(self) -> None:
        from selva_workers.tools.git_tool import GitTool

        tool = GitTool()
        tool.bash = MagicMock()
        tool.bash.execute = AsyncMock(
            return_value=MagicMock(success=True, stdout="", stderr="", return_code=0)
        )

        await tool.push("/repo", "main", token="ghp_token")

        # Should have been called twice: configure_credentials + push
        assert tool.bash.execute.call_count == 2
        first_cmd = tool.bash.execute.call_args_list[0][0][0]
        assert "credential.helper" in first_cmd

    @pytest.mark.asyncio
    async def test_push_without_token_skips_credentials(self) -> None:
        from selva_workers.tools.git_tool import GitTool

        tool = GitTool()
        tool.bash = MagicMock()
        tool.bash.execute = AsyncMock(
            return_value=MagicMock(success=True, stdout="", stderr="", return_code=0)
        )

        await tool.push("/repo", "main")

        # Only the push command, no credential config
        assert tool.bash.execute.call_count == 1
        cmd = tool.bash.execute.call_args[0][0]
        assert "push" in cmd

    @pytest.mark.asyncio
    async def test_push_with_token_none_skips_credentials(self) -> None:
        from selva_workers.tools.git_tool import GitTool

        tool = GitTool()
        tool.bash = MagicMock()
        tool.bash.execute = AsyncMock(
            return_value=MagicMock(success=True, stdout="", stderr="", return_code=0)
        )

        await tool.push("/repo", "main", token=None)

        assert tool.bash.execute.call_count == 1
