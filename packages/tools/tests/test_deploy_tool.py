"""Tests for DeployTool and DeployStatusTool (Gap C)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestDeployTool:
    """DeployTool triggers Enclii deployments."""

    def test_schema_requires_service(self) -> None:
        from selva_tools.builtins.deploy import DeployTool

        tool = DeployTool()
        schema = tool.parameters_schema()
        assert "service" in schema["required"]
        assert "environment" in schema["properties"]
        assert "image_tag" in schema["properties"]

    @pytest.mark.asyncio
    async def test_missing_env_vars_returns_error(self) -> None:
        from selva_tools.builtins.deploy import DeployTool

        tool = DeployTool()
        with patch.dict("os.environ", {}, clear=True):
            result = await tool.execute(service="web")

        assert not result.success
        assert "ENCLII_API_URL" in (result.error or "")

    @pytest.mark.asyncio
    async def test_successful_deploy(self) -> None:
        from selva_tools.builtins.deploy import DeployTool

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "deploy_id": "dep-123",
            "status": "pending",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)

        tool = DeployTool()
        env = {
            "ENCLII_API_URL": "https://enclii.test",
            "ENCLII_DEPLOY_TOKEN": "tok-123",
        }
        with (
            patch.dict("os.environ", env, clear=False),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await tool.execute(service="web", environment="staging", image_tag="v1.2.3")

        assert result.success
        assert result.data["deploy_id"] == "dep-123"

    def test_tool_name_and_description(self) -> None:
        from selva_tools.builtins.deploy import DeployTool

        tool = DeployTool()
        assert tool.name == "deploy_trigger"
        assert "deploy" in tool.description.lower()


class TestDeployStatusTool:
    """DeployStatusTool checks Enclii deployment status."""

    def test_schema_requires_deploy_id(self) -> None:
        from selva_tools.builtins.deploy import DeployStatusTool

        tool = DeployStatusTool()
        schema = tool.parameters_schema()
        assert "deploy_id" in schema["required"]

    @pytest.mark.asyncio
    async def test_missing_env_vars_returns_error(self) -> None:
        from selva_tools.builtins.deploy import DeployStatusTool

        tool = DeployStatusTool()
        with patch.dict("os.environ", {}, clear=True):
            result = await tool.execute(deploy_id="dep-123")

        assert not result.success

    @pytest.mark.asyncio
    async def test_successful_status_check(self) -> None:
        from selva_tools.builtins.deploy import DeployStatusTool

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "deploy_id": "dep-123",
            "status": "running",
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        tool = DeployStatusTool()
        env = {
            "ENCLII_API_URL": "https://enclii.test",
            "ENCLII_DEPLOY_TOKEN": "tok-123",
        }
        with (
            patch.dict("os.environ", env, clear=False),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            result = await tool.execute(deploy_id="dep-123")

        assert result.success
        assert result.data["status"] == "running"

    def test_tool_name(self) -> None:
        from selva_tools.builtins.deploy import DeployStatusTool

        tool = DeployStatusTool()
        assert tool.name == "deploy_status"


class TestDeployToolsInRegistry:
    """Deploy tools are registered in get_builtin_tools()."""

    def test_deploy_tools_in_registry(self) -> None:
        from selva_tools.builtins import get_builtin_tools

        tools = get_builtin_tools()
        names = {t.name for t in tools}
        assert "deploy_trigger" in names
        assert "deploy_status" in names
