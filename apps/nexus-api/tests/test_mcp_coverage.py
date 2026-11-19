"""Coverage contract + drift guard for the native MCP (RFC 0051 standard §3).

Walks the live FastAPI app: every route under the guarded prefixes must be
COVERED by a tool or EXEMPTED with a reason, every entry must name a live
route, and every covered route's response model must be the tool's
``outputSchema`` (the tool and the HTTP read cannot drift).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute

from nexus_api.main import app
from nexus_api.mcp import coverage
from nexus_api.mcp.tools import TOOLS
from nexus_api.schemas.inference_usage import InferenceUsageReport


def guarded_routes(application: FastAPI) -> dict[str, APIRoute]:
    routes: dict[str, APIRoute] = {}
    for route in application.routes:
        if isinstance(route, APIRoute) and route.path.startswith(coverage.GUARDED_PREFIXES):
            for method in route.methods:
                if method != "HEAD":
                    routes[f"{method} {route.path}"] = route
    return routes


def undecided(application: FastAPI) -> list[str]:
    decided = set(coverage.COVERED) | set(coverage.EXEMPTED)
    return sorted(set(guarded_routes(application)) - decided)


def test_every_guarded_route_is_decided() -> None:
    assert undecided(app) == [], "add each new route to mcp/coverage.py COVERED or EXEMPTED"


def test_no_stale_entries() -> None:
    live = set(guarded_routes(app))
    assert sorted((set(coverage.COVERED) | set(coverage.EXEMPTED)) - live) == []


def test_covered_and_exempted_are_disjoint_and_reasoned() -> None:
    assert not set(coverage.COVERED) & set(coverage.EXEMPTED)
    assert all(reason.strip() for reason in coverage.EXEMPTED.values())


def test_covered_entries_name_real_tools() -> None:
    assert set(coverage.COVERED.values()) <= set(TOOLS)
    assert set(TOOLS) <= set(coverage.COVERED.values()), "every tool maps to an HTTP read"


def test_write_and_money_routes_stay_exempted() -> None:
    for key in guarded_routes(app):
        if not key.startswith("GET "):
            assert key in coverage.EXEMPTED, f"{key} is not a read; it cannot be a tool"


def test_covered_route_response_model_is_the_tool_output_schema() -> None:
    routes = guarded_routes(app)
    route = routes["GET /api/v1/billing/inference-usage"]
    assert route.response_model is InferenceUsageReport
    assert TOOLS["inference_usage"].output_schema == InferenceUsageReport.model_json_schema(
        mode="serialization"
    )
    query = {param.alias for param in route.dependant.query_params}
    assert set(TOOLS["inference_usage"].input_schema["properties"]) == query


def test_drift_guard_fails_on_an_uncovered_route() -> None:
    probe = FastAPI()
    for route in app.routes:
        probe.router.routes.append(route)

    @probe.get("/api/v1/billing/new-spend-read")
    async def _new_spend_read() -> dict[str, str]:
        return {}

    assert undecided(probe) == ["GET /api/v1/billing/new-spend-read"]
