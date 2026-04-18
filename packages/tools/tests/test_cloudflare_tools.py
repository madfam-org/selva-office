"""Tests for Cloudflare tools (zone CRUD + redirects)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.cloudflare import (
    CloudflareCreateDnsRecordTool,
    CloudflareCreateRedirectRuleTool,
    CloudflareCreateZoneTool,
    CloudflareListPageRulesTool,
    CloudflareListZonesTool,
    get_cloudflare_tools,
)


# -- Registry + metadata ------------------------------------------------------


class TestRegistry:
    def test_get_cloudflare_tools_returns_all_six(self) -> None:
        tools = get_cloudflare_tools()
        names = {t.name for t in tools}
        assert names == {
            "cloudflare_create_zone",
            "cloudflare_list_zones",
            "cloudflare_create_dns_record",
            "cloudflare_list_dns_records",
            "cloudflare_create_redirect_rule",
            "cloudflare_list_page_rules",
        }

    def test_each_tool_has_parameters_schema(self) -> None:
        for t in get_cloudflare_tools():
            schema = t.parameters_schema()
            assert schema["type"] == "object"
            assert "properties" in schema


# -- Credential gating --------------------------------------------------------


class TestCredentialCheck:
    @pytest.mark.asyncio
    async def test_missing_token_fails_every_tool(self) -> None:
        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", ""
        ), patch("selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"):
            r = await CloudflareCreateZoneTool().execute(domain="x.com")
            assert r.success is False
            assert "CLOUDFLARE_API_TOKEN" in (r.error or "")

    @pytest.mark.asyncio
    async def test_missing_account_id_fails_zone_create(self) -> None:
        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch("selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", ""):
            r = await CloudflareCreateZoneTool().execute(domain="x.com")
            assert r.success is False
            assert "CLOUDFLARE_ACCOUNT_ID" in (r.error or "")


# -- Zone create --------------------------------------------------------------


class TestCreateZone:
    @pytest.mark.asyncio
    async def test_success_returns_id_and_name_servers(self) -> None:
        mock_body = {
            "success": True,
            "result": {
                "id": "zone-123",
                "name": "example.com",
                "status": "pending",
                "name_servers": ["a.ns.cloudflare.com", "b.ns.cloudflare.com"],
            },
            "errors": [],
        }
        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request",
            new=AsyncMock(return_value=mock_body),
        ):
            r = await CloudflareCreateZoneTool().execute(domain="example.com")
            assert r.success is True
            assert r.data["zone_id"] == "zone-123"
            assert r.data["name_servers"] == [
                "a.ns.cloudflare.com",
                "b.ns.cloudflare.com",
            ]

    @pytest.mark.asyncio
    async def test_cloudflare_error_bubbles_up(self) -> None:
        mock_body = {
            "success": False,
            "errors": [{"message": "domain already exists"}],
        }
        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request",
            new=AsyncMock(return_value=mock_body),
        ):
            r = await CloudflareCreateZoneTool().execute(domain="dup.com")
            assert r.success is False
            assert "domain already exists" in (r.error or "")


# -- Zone list ----------------------------------------------------------------


class TestListZones:
    @pytest.mark.asyncio
    async def test_list_returns_summary(self) -> None:
        mock_body = {
            "success": True,
            "result": [
                {
                    "name": "a.com",
                    "id": "id-a",
                    "status": "active",
                    "name_servers": ["x.ns", "y.ns"],
                },
                {
                    "name": "b.com",
                    "id": "id-b",
                    "status": "pending",
                    "name_servers": ["x.ns", "y.ns"],
                },
            ],
            "errors": [],
        }
        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request",
            new=AsyncMock(return_value=mock_body),
        ):
            r = await CloudflareListZonesTool().execute()
            assert r.success is True
            assert len(r.data["zones"]) == 2


# -- DNS record create --------------------------------------------------------


class TestCreateDnsRecord:
    @pytest.mark.asyncio
    async def test_proxied_defaults_true(self) -> None:
        captured: dict = {}

        async def fake_request(method, path, json=None):
            captured["json"] = json
            return {
                "success": True,
                "result": {
                    "id": "r-1",
                    "type": "A",
                    "name": "example.com",
                    "content": "1.2.3.4",
                    "proxied": True,
                },
                "errors": [],
            }

        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request", new=fake_request
        ):
            r = await CloudflareCreateDnsRecordTool().execute(
                zone_id="z",
                type="A",
                name="example.com",
                content="1.2.3.4",
            )
            assert r.success is True
            assert captured["json"]["proxied"] is True
            assert captured["json"]["ttl"] == 1


# -- Redirect rule ------------------------------------------------------------


class TestCreateRedirectRule:
    @pytest.mark.asyncio
    async def test_wildcard_pagerule_shape(self) -> None:
        captured: dict = {}

        async def fake_request(method, path, json=None):
            captured["path"] = path
            captured["json"] = json
            return {
                "success": True,
                "result": {"id": "pr-1", "priority": 1, "status": "active"},
                "errors": [],
            }

        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request", new=fake_request
        ):
            r = await CloudflareCreateRedirectRuleTool().execute(
                zone_id="z",
                domain="old.example",
                target="https://new.example",
            )
            assert r.success is True
            assert captured["path"] == "zones/z/pagerules"
            # Target pattern: "*old.example/*" matches apex + subdomains + paths
            assert (
                captured["json"]["targets"][0]["constraint"]["value"]
                == "*old.example/*"
            )
            # Forwarding substitutes $2 for the captured path
            assert (
                captured["json"]["actions"][0]["value"]["url"]
                == "https://new.example/$2"
            )
            assert captured["json"]["actions"][0]["value"]["status_code"] == 301

    @pytest.mark.asyncio
    async def test_trailing_slash_stripped_from_target(self) -> None:
        captured: dict = {}

        async def fake_request(method, path, json=None):
            captured["json"] = json
            return {
                "success": True,
                "result": {"id": "pr-1"},
                "errors": [],
            }

        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request", new=fake_request
        ):
            await CloudflareCreateRedirectRuleTool().execute(
                zone_id="z",
                domain="old.example",
                target="https://new.example/",
            )
            # No double slash — we strip trailing / from target before appending $2.
            assert (
                captured["json"]["actions"][0]["value"]["url"]
                == "https://new.example/$2"
            )

    @pytest.mark.asyncio
    async def test_custom_status_code_302(self) -> None:
        captured: dict = {}

        async def fake_request(method, path, json=None):
            captured["json"] = json
            return {
                "success": True,
                "result": {"id": "pr-1"},
                "errors": [],
            }

        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request", new=fake_request
        ):
            await CloudflareCreateRedirectRuleTool().execute(
                zone_id="z",
                domain="o.com",
                target="https://n.com",
                status_code=302,
            )
            assert captured["json"]["actions"][0]["value"]["status_code"] == 302


# -- Page rules list ----------------------------------------------------------


class TestListPageRules:
    @pytest.mark.asyncio
    async def test_list_returns_rules(self) -> None:
        mock_body = {
            "success": True,
            "result": [{"id": "pr-1", "priority": 1, "status": "active"}],
            "errors": [],
        }
        with patch(
            "selva_tools.builtins.cloudflare.CF_TOKEN", "tok"
        ), patch(
            "selva_tools.builtins.cloudflare.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare._request",
            new=AsyncMock(return_value=mock_body),
        ):
            r = await CloudflareListPageRulesTool().execute(zone_id="z")
            assert r.success is True
            assert len(r.data["rules"]) == 1
