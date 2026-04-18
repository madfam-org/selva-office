"""Tests for ArgoCD Application tools."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.argocd import (
    ArgocdGetAppTool,
    ArgocdListAppsTool,
    ArgocdRefreshAppTool,
    ArgocdSyncAppTool,
    get_argocd_tools,
)


class TestRegistry:
    def test_four_tools_exported(self) -> None:
        tools = get_argocd_tools()
        names = {t.name for t in tools}
        assert names == {
            "argocd_list_apps",
            "argocd_get_app",
            "argocd_sync_app",
            "argocd_refresh_app",
        }

    def test_schemas_valid(self) -> None:
        for t in get_argocd_tools():
            s = t.parameters_schema()
            assert s["type"] == "object"


# -- list --------------------------------------------------------------------


class TestListApps:
    @pytest.mark.asyncio
    async def test_list_returns_summary(self) -> None:
        body = {
            "items": [
                {
                    "metadata": {"name": "madlab-services"},
                    "spec": {
                        "project": "default",
                        "destination": {"namespace": "madlab"},
                    },
                    "status": {
                        "sync": {"status": "Synced", "revision": "abc"},
                        "health": {"status": "Healthy"},
                    },
                }
            ]
        }
        with patch(
            "selva_tools.builtins.argocd._request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await ArgocdListAppsTool().execute()
            assert r.success is True
            assert r.data["applications"][0]["name"] == "madlab-services"
            assert r.data["applications"][0]["sync"] == "Synced"

    @pytest.mark.asyncio
    async def test_filter_by_namespace(self) -> None:
        body = {
            "items": [
                {
                    "metadata": {"name": "a"},
                    "spec": {"destination": {"namespace": "x"}},
                    "status": {},
                },
                {
                    "metadata": {"name": "b"},
                    "spec": {"destination": {"namespace": "y"}},
                    "status": {},
                },
            ]
        }
        with patch(
            "selva_tools.builtins.argocd._request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await ArgocdListAppsTool().execute(namespace="y")
            assert len(r.data["applications"]) == 1
            assert r.data["applications"][0]["name"] == "b"

    @pytest.mark.asyncio
    async def test_filter_by_name_substring(self) -> None:
        body = {
            "items": [
                {"metadata": {"name": "madlab-services"}, "spec": {}, "status": {}},
                {"metadata": {"name": "routecraft-services"}, "spec": {}, "status": {}},
            ]
        }
        with patch(
            "selva_tools.builtins.argocd._request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await ArgocdListAppsTool().execute(name_contains="route")
            assert len(r.data["applications"]) == 1

    @pytest.mark.asyncio
    async def test_error_bubbles_up(self) -> None:
        with patch(
            "selva_tools.builtins.argocd._request",
            new=AsyncMock(return_value=(401, {"message": "unauthenticated"})),
        ):
            r = await ArgocdListAppsTool().execute()
            assert r.success is False
            assert "unauthenticated" in (r.error or "")


# -- get ---------------------------------------------------------------------


class TestGetApp:
    @pytest.mark.asyncio
    async def test_returns_conditions_and_resources(self) -> None:
        body = {
            "status": {
                "sync": {"status": "OutOfSync", "revision": "abc"},
                "health": {"status": "Degraded"},
                "conditions": [
                    {
                        "type": "SyncError",
                        "message": "admission webhook denied the request",
                    }
                ],
                "resources": [
                    {
                        "kind": "Deployment",
                        "name": "madlab-server",
                        "namespace": "madlab",
                        "status": "OutOfSync",
                        "health": {"status": "Missing"},
                    }
                ],
            }
        }
        with patch(
            "selva_tools.builtins.argocd._request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await ArgocdGetAppTool().execute(name="madlab-services")
            assert r.success is True
            assert r.data["sync"]["status"] == "OutOfSync"
            assert r.data["conditions"][0]["type"] == "SyncError"
            assert r.data["resources"][0]["kind"] == "Deployment"

    @pytest.mark.asyncio
    async def test_condition_message_truncated(self) -> None:
        long_msg = "x" * 2000
        body = {
            "status": {
                "conditions": [{"type": "SyncError", "message": long_msg}],
            }
        }
        with patch(
            "selva_tools.builtins.argocd._request",
            new=AsyncMock(return_value=(200, body)),
        ):
            r = await ArgocdGetAppTool().execute(name="x")
            assert len(r.data["conditions"][0]["message"]) == 500


# -- sync --------------------------------------------------------------------


class TestSyncApp:
    @pytest.mark.asyncio
    async def test_sync_payload_shape(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None, params=None):
            captured["method"] = method
            captured["path"] = path
            captured["json_body"] = json_body
            return 200, {"operation": {"sync": {"revision": "abc"}}}

        with patch("selva_tools.builtins.argocd._request", new=fake):
            r = await ArgocdSyncAppTool().execute(
                name="x", revision="main", prune=True, force=True
            )
            assert r.success is True
            assert captured["method"] == "POST"
            assert captured["path"].endswith("/x/sync")
            assert captured["json_body"]["prune"] is True
            assert captured["json_body"]["strategy"]["apply"]["force"] is True
            assert captured["json_body"]["revision"] == "main"

    @pytest.mark.asyncio
    async def test_sync_defaults_prune_false(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None, params=None):
            captured["json_body"] = json_body
            return 200, {}

        with patch("selva_tools.builtins.argocd._request", new=fake):
            await ArgocdSyncAppTool().execute(name="x")
            assert captured["json_body"]["prune"] is False
            assert captured["json_body"]["dryRun"] is False
            assert "revision" not in captured["json_body"]


# -- refresh -----------------------------------------------------------------


class TestRefreshApp:
    @pytest.mark.asyncio
    async def test_refresh_hard_is_default(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None, params=None):
            captured["params"] = params
            return 200, {}

        with patch("selva_tools.builtins.argocd._request", new=fake):
            r = await ArgocdRefreshAppTool().execute(name="x")
            assert r.success is True
            assert captured["params"] == {"refresh": "hard"}

    @pytest.mark.asyncio
    async def test_refresh_normal_override(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None, params=None):
            captured["params"] = params
            return 200, {}

        with patch("selva_tools.builtins.argocd._request", new=fake):
            await ArgocdRefreshAppTool().execute(name="x", type="normal")
            assert captured["params"] == {"refresh": "normal"}
