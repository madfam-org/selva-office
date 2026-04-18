"""Tests for cloudflare_tunnel, cloudflare_r2, cloudflare_saas tools.

Grouped in one file because all three share the same Cloudflare API shape
and credential surface — reduces boilerplate.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.cloudflare_r2 import (
    R2BucketCreateTool,
    R2BucketDeleteTool,
    R2BucketListTool,
    R2CorsSetTool,
    get_r2_tools,
)
from selva_tools.builtins.cloudflare_saas import (
    CfSaasHostnameAddTool,
    CfSaasHostnameDeleteTool,
    CfSaasHostnameListTool,
    CfSaasHostnameStatusTool,
    get_cloudflare_saas_tools,
)
from selva_tools.builtins.cloudflare_tunnel import (
    CfTunnelCreateTool,
    CfTunnelGetIngressTool,
    CfTunnelListTool,
    CfTunnelPutIngressTool,
    get_cloudflare_tunnel_tools,
)


# -- Tunnel ------------------------------------------------------------------


class TestTunnelRegistry:
    def test_four_tools(self) -> None:
        names = {t.name for t in get_cloudflare_tunnel_tools()}
        assert names == {
            "cf_tunnel_list",
            "cf_tunnel_create",
            "cf_tunnel_get_ingress",
            "cf_tunnel_put_ingress",
        }


class TestTunnelCreate:
    @pytest.mark.asyncio
    async def test_secret_auto_generated_when_absent(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None):
            captured["json_body"] = json_body
            return {
                "success": True,
                "result": {"id": "tid-123", "name": "x"},
                "errors": [],
            }

        with patch(
            "selva_tools.builtins.cloudflare_tunnel.CF_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.cloudflare_tunnel.CF_ACCOUNT_ID", "acc"
        ), patch("selva_tools.builtins.cloudflare_tunnel._request", new=fake):
            r = await CfTunnelCreateTool().execute(name="foundry")
            assert r.success is True
            assert r.data["tunnel_id"] == "tid-123"
            # Auto-generated secret is base64, reasonable length
            assert len(r.data["tunnel_secret"]) >= 32
            assert captured["json_body"]["tunnel_secret"]

    @pytest.mark.asyncio
    async def test_cname_target_in_response(self) -> None:
        with patch(
            "selva_tools.builtins.cloudflare_tunnel.CF_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.cloudflare_tunnel.CF_ACCOUNT_ID", "acc"
        ), patch(
            "selva_tools.builtins.cloudflare_tunnel._request",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "result": {"id": "abc-uuid", "name": "foundry"},
                    "errors": [],
                }
            ),
        ):
            r = await CfTunnelCreateTool().execute(name="foundry")
            assert r.data["cname_target"] == "abc-uuid.cfargotunnel.com"


class TestTunnelIngressValidation:
    @pytest.mark.asyncio
    async def test_missing_catchall_rejected(self) -> None:
        with patch("selva_tools.builtins.cloudflare_tunnel.CF_TOKEN", "t"), patch(
            "selva_tools.builtins.cloudflare_tunnel.CF_ACCOUNT_ID", "acc"
        ):
            r = await CfTunnelPutIngressTool().execute(
                tunnel_id="t",
                ingress=[
                    {"hostname": "a.example", "service": "http://a"},
                    {"hostname": "b.example", "service": "http://b"},
                ],
            )
            assert r.success is False
            assert "catch-all" in (r.error or "")

    @pytest.mark.asyncio
    async def test_valid_ingress_with_catchall_accepted(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None):
            captured["path"] = path
            captured["json_body"] = json_body
            return {"success": True, "result": {}, "errors": []}

        with patch(
            "selva_tools.builtins.cloudflare_tunnel.CF_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.cloudflare_tunnel.CF_ACCOUNT_ID", "acc"
        ), patch("selva_tools.builtins.cloudflare_tunnel._request", new=fake):
            r = await CfTunnelPutIngressTool().execute(
                tunnel_id="t",
                ingress=[
                    {"hostname": "a.example", "service": "http://a"},
                    {"service": "http_status:404"},
                ],
            )
            assert r.success is True
            assert captured["json_body"]["config"]["ingress"][-1] == {
                "service": "http_status:404"
            }


# -- R2 ----------------------------------------------------------------------


class TestR2Registry:
    def test_four_tools(self) -> None:
        names = {t.name for t in get_r2_tools()}
        assert names == {
            "r2_bucket_list",
            "r2_bucket_create",
            "r2_bucket_delete",
            "r2_cors_set",
        }


class TestR2BucketCreate:
    @pytest.mark.asyncio
    async def test_auto_location_omits_location_hint(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None):
            captured["json_body"] = json_body
            return {
                "success": True,
                "result": {"name": "subtext-audio"},
                "errors": [],
            }

        with patch(
            "selva_tools.builtins.cloudflare_r2.CF_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.cloudflare_r2.CF_ACCOUNT_ID", "acc"
        ), patch("selva_tools.builtins.cloudflare_r2._request", new=fake):
            r = await R2BucketCreateTool().execute(name="subtext-audio")
            assert r.success is True
            # 'auto' means no locationHint sent
            assert "locationHint" not in captured["json_body"]
            assert captured["json_body"]["storageClass"] == "Standard"

    @pytest.mark.asyncio
    async def test_explicit_location_passes_through(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None):
            captured["json_body"] = json_body
            return {"success": True, "result": {"name": "x"}, "errors": []}

        with patch(
            "selva_tools.builtins.cloudflare_r2.CF_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.cloudflare_r2.CF_ACCOUNT_ID", "acc"
        ), patch("selva_tools.builtins.cloudflare_r2._request", new=fake):
            await R2BucketCreateTool().execute(
                name="x", location="WNAM", storage_class="InfrequentAccess"
            )
            assert captured["json_body"]["locationHint"] == "WNAM"
            assert captured["json_body"]["storageClass"] == "InfrequentAccess"

    @pytest.mark.asyncio
    async def test_endpoint_in_response(self) -> None:
        with patch(
            "selva_tools.builtins.cloudflare_r2.CF_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.cloudflare_r2.CF_ACCOUNT_ID", "acc123"
        ), patch(
            "selva_tools.builtins.cloudflare_r2._request",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "result": {"name": "subtext-audio"},
                    "errors": [],
                }
            ),
        ):
            r = await R2BucketCreateTool().execute(name="subtext-audio")
            assert (
                r.data["endpoint"]
                == "https://acc123.r2.cloudflarestorage.com/subtext-audio"
            )


# -- SaaS --------------------------------------------------------------------


class TestSaasRegistry:
    def test_four_tools(self) -> None:
        names = {t.name for t in get_cloudflare_saas_tools()}
        assert names == {
            "cf_saas_hostname_add",
            "cf_saas_hostname_status",
            "cf_saas_hostname_list",
            "cf_saas_hostname_delete",
        }


class TestSaasHostnameAdd:
    @pytest.mark.asyncio
    async def test_ownership_verification_surfaced(self) -> None:
        with patch(
            "selva_tools.builtins.cloudflare_saas.CF_TOKEN", "t"
        ), patch(
            "selva_tools.builtins.cloudflare_saas._request",
            new=AsyncMock(
                return_value={
                    "success": True,
                    "result": {
                        "id": "hn-1",
                        "hostname": "app.tenant.com",
                        "status": "pending",
                        "ssl": {"status": "pending_validation"},
                        "ownership_verification": {
                            "type": "txt",
                            "name": "_cf-custom-hostname.app.tenant.com",
                            "value": "abcd-uuid",
                        },
                    },
                    "errors": [],
                }
            ),
        ):
            r = await CfSaasHostnameAddTool().execute(
                zone_id="z", hostname="app.tenant.com"
            )
            assert r.success is True
            assert r.data["ownership_verification"]["type"] == "txt"
            assert (
                r.data["ownership_verification"]["name"]
                == "_cf-custom-hostname.app.tenant.com"
            )

    @pytest.mark.asyncio
    async def test_default_ssl_method_http(self) -> None:
        captured: dict = {}

        async def fake(method, path, json_body=None):
            captured["json_body"] = json_body
            return {
                "success": True,
                "result": {"id": "x", "hostname": "x", "status": "pending", "ssl": {}},
                "errors": [],
            }

        with patch(
            "selva_tools.builtins.cloudflare_saas.CF_TOKEN", "t"
        ), patch("selva_tools.builtins.cloudflare_saas._request", new=fake):
            await CfSaasHostnameAddTool().execute(
                zone_id="z", hostname="app.tenant.com"
            )
            assert captured["json_body"]["ssl"]["method"] == "http"
            assert captured["json_body"]["ssl"]["type"] == "dv"
