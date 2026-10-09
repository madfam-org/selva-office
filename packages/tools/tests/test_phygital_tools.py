"""Tests for phygital tools."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import httpx
import pytest

from selva_tools.audience import Audience
from selva_tools.base import BaseTool
from selva_tools.builtins import get_builtin_tools, phygital_tools, service_auth
from selva_tools.builtins.operations import InventoryCheckTool
from selva_tools.builtins.phygital_tools import (
    GenerateParametricModelTool,
    GenerateQuoteTool,
    GetProductionOrderStatusTool,
    RunDFMAnalysisTool,
)

CONTRACT: dict[str, Any] = json.loads(
    (Path(__file__).parent / "fixtures" / "phygital_routes.json").read_text()
)

BASE_URLS = {
    "yantra4d": "https://yantra.test",
    "cotiza": "https://cotiza.test",
    "pravara-mes": "https://pravara.test",
}
TOKENS = {
    "yantra4d": "yantra-service-token",
    "cotiza": "cotiza-service-token",
    "pravara-mes": "pravara-service-token",
}
TOKEN_ATTRS = {
    "yantra4d": "YANTRA4D_API_TOKEN",
    "cotiza": "COTIZA_API_TOKEN",
    "pravara-mes": "PRAVARA_MES_API_TOKEN",
}
TOKEN_ENVS = {
    "yantra4d": service_auth.YANTRA4D_TOKEN_ENV,
    "cotiza": service_auth.COTIZA_TOKEN_ENV,
    "pravara-mes": service_auth.PRAVARA_TOKEN_ENV,
}
ORDER_ID = "7b0c6c2e-3f5d-4a8e-9c1b-2d4e6f8a0b1c"
GEOMETRY = {
    "volume_cm3": 1.2,
    "surface_area_cm2": 6.0,
    "bounding_box_mm": {"x": 10, "y": 20, "z": 30},
}

RENDER_BODY = {
    "status": "success",
    "parts": [{"type": "body", "url": "/static/demo_stl_abc123_body.stl", "size_bytes": 2048}],
    "log": "",
    "request_id": "r_1",
}
THICKNESS_BODY = {
    "status": "success",
    "project": "demo",
    "mesh_file": "demo_stl_abc123_body.stl",
    "analysis": {
        "thicknesses": [1.5, 2.0],
        "points": [[0, 0, 0], [1, 1, 1]],
        "min": 1.5,
        "max": 2.0,
        "mean": 1.75,
        "thin_wall_count": 0,
        "sample_count": 5000,
        "valid_hits": 2,
    },
}
OVERHANG_BODY = {
    "status": "success",
    "project": "demo",
    "mesh_file": "demo_stl_abc123_body.stl",
    "analysis": {
        "angles": [50.0],
        "points": [[0, 0, 0]],
        "threshold_deg": 45.0,
        "overhang_count": 1,
        "min_angle": 50.0,
        "max_angle": 50.0,
        "mean_angle": 50.0,
        "sample_count": 5000,
    },
}
ORDER_BODY = {"id": ORDER_ID, "status": "in_progress"}
INVENTORY_BODY = {
    "data": [
        {"sku": "SKU-0010", "quantity_available": 99, "unit": "pcs"},
        {
            "sku": "SKU-001",
            "unit": "pcs",
            "quantity_on_hand": 10,
            "quantity_reserved": 3,
            "quantity_available": 7,
        },
    ],
    "total": 2,
    "limit": 100,
    "offset": 0,
}
QUOTE_BODY = {
    "quoteId": "q_123",
    "totalPrice": 125.5,
    "currency": "MXN",
    "market_context": {"market_verified": True},
}


def _default_body(url: str) -> dict[str, Any]:
    if url.endswith("/api/render"):
        return RENDER_BODY
    if url.endswith("/analyze/thickness"):
        return THICKNESS_BODY
    if url.endswith("/analyze/overhang"):
        return OVERHANG_BODY
    if "/v1/orders/" in url:
        return ORDER_BODY
    if url.endswith("/v1/inventory"):
        return INVENTORY_BODY
    return QUOTE_BODY


class _RecordingClient:
    """Stand-in for ``httpx.AsyncClient`` that records every request."""

    calls: list[dict[str, Any]] = []
    #: URL suffix -> (status code, JSON body) overriding the default response.
    responses: dict[str, tuple[int, Any]] = {}

    def __init__(self, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> _RecordingClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    def _respond(
        self,
        method: str,
        url: str,
        payload: Any,
        headers: dict[str, str] | None,
        params: dict[str, str] | None = None,
    ) -> httpx.Response:
        call = {"method": method, "url": url, "json": payload, "headers": headers}
        if params is not None:
            call["params"] = params
        self.calls.append(call)
        status, body = 200, _default_body(url)
        for suffix, response in self.responses.items():
            if url.endswith(suffix):
                status, body = response
        return httpx.Response(status, request=httpx.Request(method, url), json=body)

    async def post(
        self, url: str, json: Any = None, headers: dict[str, str] | None = None, **_: Any
    ) -> httpx.Response:
        return self._respond("POST", url, json, headers)

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        **_: Any,
    ) -> httpx.Response:
        return self._respond("GET", url, None, headers, params)


@pytest.fixture(autouse=True)
def _configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _RecordingClient.calls = []
    _RecordingClient.responses = {}
    monkeypatch.setattr(phygital_tools, "YANTRA4D_API_URL", BASE_URLS["yantra4d"])
    monkeypatch.setattr(phygital_tools, "COTIZA_API_URL", BASE_URLS["cotiza"])
    monkeypatch.setattr(phygital_tools, "PRAVARA_MES_API_URL", BASE_URLS["pravara-mes"])
    for service, attr in TOKEN_ATTRS.items():
        monkeypatch.setattr(phygital_tools, attr, TOKENS[service])
    # inventory_check reads its configuration from the environment at call time.
    for names in TOKEN_ENVS.values():
        for name in names:
            monkeypatch.delenv(name, raising=False)
    # These tests exercise the static-token path; machine-edge client
    # credentials are covered in test_service_auth.py.
    for edge in (service_auth.YANTRA4D_EDGE, service_auth.PRAVARA_EDGE):
        monkeypatch.delenv(edge.client_id_env, raising=False)
        monkeypatch.delenv(edge.client_secret_env, raising=False)
    service_auth.reset_token_cache()
    monkeypatch.setenv("PRAVARA_MES_API_URL", BASE_URLS["pravara-mes"])
    monkeypatch.setenv("PRAVARA_MES_API_TOKEN", TOKENS["pravara-mes"])
    monkeypatch.setattr(phygital_tools.httpx, "AsyncClient", _RecordingClient)


def _expected_headers(service: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKENS[service]}",
        "X-Service-Actor": "selva-agent",
    }


def _route_regex(path: str) -> re.Pattern[str]:
    """Anchored regex for a Flask (``<slug>``) or Gin (``:id``) path pattern."""
    literals = re.split(r"<[^>]+>|:[A-Za-z_]+", path)
    return re.compile("^" + "[^/]+".join(re.escape(part) for part in literals) + "$")


def _service_and_path(url: str) -> tuple[str, str]:
    for service, base in BASE_URLS.items():
        if url.startswith(base + "/"):
            return service, url[len(base) :]
    raise AssertionError(f"request to an unknown host: {url}")


def _matching_routes(tool_name: str, call: dict[str, Any]) -> list[dict[str, Any]]:
    service, path = _service_and_path(call["url"])
    return [
        route
        for route in CONTRACT["routes"]
        if route["tool"] == tool_name
        and route["service"] == service
        and route["method"] == call["method"]
        and _route_regex(route["path"]).match(path)
    ]


# (tool class, kwargs, service whose token the call must carry)
INVOCATIONS: list[tuple[type[BaseTool], dict[str, Any], str]] = [
    (
        GenerateParametricModelTool,
        {"project_slug": "demo", "parameters": {"width": 40}, "mode": "body"},
        "yantra4d",
    ),
    (RunDFMAnalysisTool, {"project_slug": "demo project"}, "yantra4d"),
    (GenerateQuoteTool, {"project_slug": "demo"}, "yantra4d"),
    (GenerateQuoteTool, {"geometry": GEOMETRY, "project": {"name": "Bracket"}}, "cotiza"),
    (GetProductionOrderStatusTool, {"order_id": ORDER_ID}, "pravara-mes"),
    (InventoryCheckTool, {"sku": "SKU-001"}, "pravara-mes"),
]
INVOCATION_IDS = [
    "render",
    "dfm",
    "quote-via-yantra4d",
    "quote-via-cotiza",
    "order-status",
    "inventory",
]


class TestRouteContract:
    def test_fixture_records_source_repo_and_commit(self) -> None:
        services = CONTRACT["services"]
        assert set(services) == set(BASE_URLS)
        for service in services.values():
            assert re.fullmatch(r"madfam-org/[a-z0-9-]+", service["repo"])
            assert re.fullmatch(r"[0-9a-f]{40}", service["commit"])
        for route in CONTRACT["routes"]:
            assert route["service"] in services
            assert route["method"] in {"GET", "POST"}
            assert route["path"].startswith("/")
            assert route["source"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool_cls", "kwargs", "service"), INVOCATIONS, ids=INVOCATION_IDS)
    async def test_every_request_matches_a_vendored_route(
        self, tool_cls: type[BaseTool], kwargs: dict[str, Any], service: str
    ) -> None:
        tool = tool_cls()
        result = await tool.execute(**kwargs)

        assert result.success, result.error
        assert _RecordingClient.calls
        for call in _RecordingClient.calls:
            assert _matching_routes(tool.name, call), (
                f"{tool.name} requested {call['method']} {call['url']}, "
                "which is not a vendored route"
            )

    @pytest.mark.asyncio
    async def test_every_vendored_route_is_exercised(self) -> None:
        exercised: set[tuple[str, str, str]] = set()
        for tool_cls, kwargs, _service in INVOCATIONS:
            _RecordingClient.calls = []
            tool = tool_cls()
            await tool.execute(**kwargs)
            for call in _RecordingClient.calls:
                for route in _matching_routes(tool.name, call):
                    exercised.add((route["tool"], route["method"], route["path"]))

        vendored = {(r["tool"], r["method"], r["path"]) for r in CONTRACT["routes"]}
        assert exercised == vendored

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool_cls", "kwargs", "service"), INVOCATIONS, ids=INVOCATION_IDS)
    async def test_every_request_carries_the_service_token(
        self, tool_cls: type[BaseTool], kwargs: dict[str, Any], service: str
    ) -> None:
        await tool_cls().execute(**kwargs)

        assert _RecordingClient.calls
        for call in _RecordingClient.calls:
            assert call["headers"] == _expected_headers(service)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("tool_cls", "kwargs", "service"), INVOCATIONS, ids=INVOCATION_IDS)
    async def test_missing_token_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tool_cls: type[BaseTool],
        kwargs: dict[str, Any],
        service: str,
    ) -> None:
        monkeypatch.setattr(phygital_tools, TOKEN_ATTRS[service], "")
        for name in TOKEN_ENVS[service]:
            monkeypatch.delenv(name, raising=False)

        result = await tool_cls().execute(**kwargs)

        assert not result.success
        assert "service token not configured" in (result.error or "")
        assert _RecordingClient.calls == []


class TestTokenResolution:
    def test_pravara_token_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        names = phygital_tools._PRAVARA_TOKEN_ENV
        assert names == (
            "PRAVARA_MES_API_TOKEN",
            "SELVA_PRAVARA_SERVICE_TOKEN",
            "SELVA_SERVICE_TOKEN",
        )
        for name in names:
            monkeypatch.delenv(name, raising=False)
        assert phygital_tools._first_env(names) == ""
        monkeypatch.setenv("SELVA_SERVICE_TOKEN", "shared")
        assert phygital_tools._first_env(names) == "shared"
        monkeypatch.setenv("SELVA_PRAVARA_SERVICE_TOKEN", "pravara-selva")
        assert phygital_tools._first_env(names) == "pravara-selva"
        monkeypatch.setenv("PRAVARA_MES_API_TOKEN", "pravara-direct")
        assert phygital_tools._first_env(names) == "pravara-direct"


class TestGenerateParametricModelTool:
    def test_schema_has_only_render_api_fields(self) -> None:
        schema = GenerateParametricModelTool().parameters_schema()
        assert set(schema["properties"]) == {"project_slug", "parameters", "mode", "export_format"}
        assert schema["required"] == ["project_slug"]
        assert schema["properties"]["export_format"]["enum"] == [
            "stl",
            "3mf",
            "off",
            "step",
            "gltf",
            "glb",
            "obj",
        ]

    @pytest.mark.asyncio
    async def test_renders_project_with_nested_parameters(self) -> None:
        result = await GenerateParametricModelTool().execute(
            project_slug="demo", parameters={"width": 40}, mode="body", export_format="3MF"
        )

        assert result.success
        assert _RecordingClient.calls[0]["url"] == "https://yantra.test/api/render"
        assert _RecordingClient.calls[0]["json"] == {
            "project": "demo",
            "parameters": {"width": 40},
            "export_format": "3mf",
            "mode": "body",
        }
        assert result.data == RENDER_BODY
        assert "1 part(s): body (2048 bytes)" in result.output

    @pytest.mark.asyncio
    async def test_omitted_mode_and_parameters(self) -> None:
        result = await GenerateParametricModelTool().execute(project_slug="demo")

        assert result.success
        assert _RecordingClient.calls[0]["json"] == {
            "project": "demo",
            "parameters": {},
            "export_format": "stl",
        }
        assert "mode: project default" in result.output

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({}, "project_slug is required"),
            ({"project_slug": "demo", "parameters": [1, 2]}, "parameters must be an object"),
            ({"project_slug": "demo", "export_format": "dwg"}, "export_format must be one of"),
        ],
    )
    async def test_invalid_input_sends_nothing(self, kwargs: dict[str, Any], message: str) -> None:
        result = await GenerateParametricModelTool().execute(**kwargs)

        assert not result.success
        assert message in (result.error or "")
        assert _RecordingClient.calls == []

    @pytest.mark.asyncio
    async def test_reports_yantra4d_refusal(self) -> None:
        _RecordingClient.responses = {
            "/api/render": (403, {"error": "Export format 'step' requires Pro tier or above."})
        }

        result = await GenerateParametricModelTool().execute(
            project_slug="demo", export_format="step"
        )

        assert not result.success
        assert "HTTP 403" in (result.error or "")
        assert "requires Pro tier or above" in (result.error or "")


class TestRunDFMAnalysisTool:
    def test_schema_drops_fictional_fields(self) -> None:
        schema = RunDFMAnalysisTool().parameters_schema()
        assert set(schema["properties"]) == {"project_slug", "sample_count", "threshold_deg"}
        assert schema["required"] == ["project_slug"]

    @pytest.mark.asyncio
    async def test_runs_thickness_and_overhang_on_latest_render(self) -> None:
        result = await RunDFMAnalysisTool().execute(
            project_slug="demo project", sample_count=2000, threshold_deg=50
        )

        assert result.success
        assert [(c["method"], c["url"], c["json"]) for c in _RecordingClient.calls] == [
            (
                "POST",
                "https://yantra.test/api/projects/demo%20project/analyze/thickness",
                {"sample_count": 2000},
            ),
            (
                "POST",
                "https://yantra.test/api/projects/demo%20project/analyze/overhang",
                {"sample_count": 2000, "threshold_deg": 50},
            ),
        ]
        assert "latest stored render" in result.output
        assert "thin walls 0 of 5000 samples" in result.output
        assert "1 of 5000 samples beyond 45 degrees" in result.output
        assert result.data["analyzed"] == "latest_render"
        thickness = result.data["thickness"]["analysis"]
        assert "thicknesses" not in thickness and "points" not in thickness
        assert thickness["omitted_sample_arrays"] == ["thicknesses", "points"]
        assert thickness["min"] == 1.5
        overhang = result.data["overhang"]["analysis"]
        assert "angles" not in overhang
        assert overhang["overhang_count"] == 1

    @pytest.mark.asyncio
    async def test_tier_refusal_is_reported(self) -> None:
        refusal = (403, {"error": "Requires pro tier or above"})
        _RecordingClient.responses = {
            "/analyze/thickness": refusal,
            "/analyze/overhang": refusal,
        }

        result = await RunDFMAnalysisTool().execute(project_slug="demo")

        assert not result.success
        assert "thickness analysis failed: HTTP 403: Requires pro tier or above" in (
            result.error or ""
        )
        assert "overhang analysis failed: HTTP 403" in (result.error or "")

    @pytest.mark.asyncio
    async def test_unrendered_project_is_reported(self) -> None:
        not_rendered = (409, {"error": "No rendered mesh found for project 'demo'. Render first."})
        _RecordingClient.responses = {
            "/analyze/thickness": not_rendered,
            "/analyze/overhang": not_rendered,
        }

        result = await RunDFMAnalysisTool().execute(project_slug="demo")

        assert not result.success
        assert "HTTP 409" in (result.error or "")
        assert "Render first" in (result.error or "")

    @pytest.mark.asyncio
    async def test_partial_failure_keeps_the_other_result(self) -> None:
        _RecordingClient.responses = {"/analyze/overhang": (500, {"error": "Analysis failed"})}

        result = await RunDFMAnalysisTool().execute(project_slug="demo")

        assert not result.success
        assert result.data["thickness"]["analysis"]["mean"] == 1.75
        assert result.data["overhang"] == {"error": "HTTP 500: Analysis failed"}

    @pytest.mark.asyncio
    async def test_invalid_sample_count_sends_nothing(self) -> None:
        result = await RunDFMAnalysisTool().execute(project_slug="demo", sample_count="many")

        assert not result.success
        assert _RecordingClient.calls == []


class TestGetProductionOrderStatusTool:
    def test_is_read_only_platform_tool(self) -> None:
        tool = GetProductionOrderStatusTool()
        assert tool.audience is Audience.PLATFORM
        assert set(tool.parameters_schema()["properties"]) == {"order_id"}
        assert "cannot create production orders" in tool.description

    @pytest.mark.asyncio
    async def test_reads_order_with_a_get(self) -> None:
        result = await GetProductionOrderStatusTool().execute(order_id=ORDER_ID.upper())

        assert result.success
        assert _RecordingClient.calls == [
            {
                "method": "GET",
                "url": f"https://pravara.test/v1/orders/{ORDER_ID}",
                "json": None,
                "headers": _expected_headers("pravara-mes"),
            }
        ]
        assert "status in_progress" in result.output
        assert result.data == ORDER_BODY

    @pytest.mark.asyncio
    async def test_rejects_non_uuid_order_id(self) -> None:
        result = await GetProductionOrderStatusTool().execute(order_id="../maintenance/work-orders")

        assert not result.success
        assert "UUID" in (result.error or "")
        assert _RecordingClient.calls == []

    @pytest.mark.asyncio
    async def test_reports_missing_scope(self) -> None:
        _RecordingClient.responses = {
            ORDER_ID: (
                403,
                {"error": "forbidden", "message": "Missing required scope: pravara-mes:read"},
            )
        }

        result = await GetProductionOrderStatusTool().execute(order_id=ORDER_ID)

        assert not result.success
        assert "HTTP 403: forbidden - Missing required scope: pravara-mes:read" in (
            result.error or ""
        )


class TestInventoryCheckTool:
    def test_is_read_only_platform_tool(self) -> None:
        tool = InventoryCheckTool()
        assert tool.audience is Audience.PLATFORM
        assert set(tool.parameters_schema()["properties"]) == {"sku"}

    @pytest.mark.asyncio
    async def test_reads_inventory_and_keeps_the_exact_sku(self) -> None:
        result = await InventoryCheckTool().execute(sku="SKU-001")

        assert result.success
        assert _RecordingClient.calls == [
            {
                "method": "GET",
                "url": "https://pravara.test/v1/inventory",
                "json": None,
                "headers": _expected_headers("pravara-mes"),
                "params": {"search": "SKU-001", "limit": "100"},
            }
        ]
        assert result.output == (
            "Inventory for SKU SKU-001: 7 pcs available (10 on hand, 3 reserved)."
        )
        assert result.data["status"] == "found"
        assert [item["sku"] for item in result.data["items"]] == ["SKU-001"]

    @pytest.mark.asyncio
    async def test_reports_unknown_sku(self) -> None:
        result = await InventoryCheckTool().execute(sku="SKU-404")

        assert result.success
        assert result.data == {"sku": "SKU-404", "status": "not_found", "items": []}

    @pytest.mark.asyncio
    async def test_explains_machine_token_refusal(self) -> None:
        _RecordingClient.responses = {
            "/v1/inventory": (
                403,
                {"error": "forbidden", "message": "Token does not contain tenant information"},
            )
        }

        result = await InventoryCheckTool().execute(sku="SKU-001")

        assert not result.success
        assert "HTTP 403" in (result.error or "")
        assert "Token does not contain tenant information" in (result.error or "")
        assert "hold pravara-mes:read and are bound to an organization" in (result.error or "")

    @pytest.mark.asyncio
    async def test_unconfigured_url_sends_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("PRAVARA_MES_API_URL")

        result = await InventoryCheckTool().execute(sku="SKU-001")

        assert result.data["status"] == "inventory_service_not_configured"
        assert _RecordingClient.calls == []


class TestRegistry:
    def test_phygital_tools_registered_without_an_order_creator(self) -> None:
        names = {tool.name for tool in get_builtin_tools()}
        assert {
            "generate_parametric_model",
            "run_dfm_analysis",
            "generate_quote",
            "get_production_order_status",
        } <= names
        assert "create_work_order" not in names


class TestGenerateQuoteTool:
    @pytest.mark.asyncio
    async def test_project_slug_uses_yantra_project_quote_endpoint(self) -> None:
        result = await GenerateQuoteTool().execute(
            project_slug="demo project",
            model_id="m_123",
            require_market_verified=True,
        )

        assert result.success
        assert _RecordingClient.calls == [
            {
                "method": "POST",
                "url": "https://yantra.test/api/projects/demo%20project/cotiza-quote-request",
                "json": {
                    "material": "PLA",
                    "quantity": 1,
                    "process": "fdm",
                    "priority": "standard",
                    "finish": "standard",
                    "currency": "MXN",
                    "notes": "",
                    "require_market_verified": True,
                    "model_id": "m_123",
                },
                "headers": _expected_headers("yantra4d"),
            }
        ]
        assert "0.00" not in result.output

    @pytest.mark.asyncio
    async def test_without_project_slug_uses_cotiza_structured_payload(self) -> None:
        result = await GenerateQuoteTool().execute(
            geometry=GEOMETRY,
            project={"name": "Bracket", "units": "mm"},
            require_market_verified=False,
        )

        assert result.success
        assert _RecordingClient.calls == [
            {
                "method": "POST",
                "url": "https://cotiza.test/quotes/from-yantra4d",
                "json": {
                    "source": "yantra4d",
                    "geometry": GEOMETRY,
                    "project": {"name": "Bracket", "units": "mm"},
                    "item": {
                        "name": "Bracket",
                        "process": "3d_fff",
                        "material": "PLA",
                        "quantity": 1,
                        "finish": "standard",
                        "options": {
                            "priority": "standard",
                            "require_market_verified": False,
                        },
                    },
                    "currency": "MXN",
                    "notes": "",
                    "require_market_verified": False,
                },
                "headers": _expected_headers("cotiza"),
            }
        ]

    @pytest.mark.asyncio
    async def test_cotiza_requires_structured_geometry_and_project(self) -> None:
        result = await GenerateQuoteTool().execute(model_id="m_123")

        assert not result.success
        assert "geometry is required" in (result.error or "")
        assert _RecordingClient.calls == []

    @pytest.mark.asyncio
    async def test_unverified_quote_fails_closed(self) -> None:
        _RecordingClient.responses = {
            "/cotiza-quote-request": (200, {"quoteId": "q_9", "totalPrice": 10})
        }

        result = await GenerateQuoteTool().execute(project_slug="demo")

        assert not result.success
        assert "not market verified" in (result.error or "")


@pytest.mark.parametrize(
    "tool_cls", [GenerateParametricModelTool, RunDFMAnalysisTool, GenerateQuoteTool]
)
def test_tools_acting_with_selvas_service_identity_are_platform_only(
    tool_cls: type[BaseTool],
) -> None:
    """The identity is not scoped to one tenant, so tenant swarms must not use it."""
    assert tool_cls.audience is Audience.PLATFORM
