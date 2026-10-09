"""Phygital Node tools — Yantra4D render and analysis, quotes, production status.

Implements Axiom III of the Swarm Governing Manifesto:
"We do not extrude until the digital twin has succeeded."

These tools bridge the digital-to-physical gap through routes the services
actually serve. ``packages/tools/tests/fixtures/phygital_routes.json`` vendors
that contract (method, path, source repo and commit) and the tests check every
request against it:

- Render an existing Yantra4D project with parameter values
  (Yantra4D ``POST /api/render``).
- Run Yantra4D's wall-thickness and overhang analyses on a project's latest
  render (``POST /api/projects/<slug>/analyze/thickness`` and ``.../overhang``).
- Request a fabrication quote through Yantra4D or Cotiza
  (Cotiza ``POST /quotes/from-yantra4d``).
- Read a Pravara-MES production order (``GET /v1/orders/:id``).

Selva does not create production orders. Cotiza prices, Dhanam bills and
Pravara executes: an order reaches Pravara when a person orders a Cotiza
quote, through Cotiza's signed dispatch to Pravara.

Every request carries the service token (``Authorization: Bearer`` plus
``X-Service-Actor: selva-agent``). Without a token a tool returns an error
and sends nothing.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any
from urllib.parse import quote

import httpx

from ..audience import Audience
from ..base import BaseTool, ToolResult
from .service_auth import COTIZA_TOKEN_ENV as _COTIZA_TOKEN_ENV
from .service_auth import PRAVARA_TOKEN_ENV as _PRAVARA_TOKEN_ENV
from .service_auth import YANTRA4D_TOKEN_ENV as _YANTRA4D_TOKEN_ENV
from .service_auth import first_env as _first_env
from .service_auth import http_error_detail as _http_error_detail
from .service_auth import missing_token as _missing_token
from .service_auth import service_auth_headers as _service_auth_headers

logger = logging.getLogger(__name__)

YANTRA4D_API_URL = os.environ.get("YANTRA4D_API_URL", "")
PRAVARA_MES_API_URL = os.environ.get("PRAVARA_MES_API_URL", "")
COTIZA_API_URL = os.environ.get("COTIZA_API_URL", "")
YANTRA4D_API_TOKEN = _first_env(_YANTRA4D_TOKEN_ENV)
COTIZA_API_TOKEN = _first_env(_COTIZA_TOKEN_ENV)
PRAVARA_MES_API_TOKEN = _first_env(_PRAVARA_TOKEN_ENV)

#: Formats Yantra4D's render API accepts. The caller's tier narrows them further.
YANTRA4D_EXPORT_FORMATS: tuple[str, ...] = ("stl", "3mf", "off", "step", "gltf", "glb", "obj")

#: Per-sample arrays in Yantra4D analysis results (up to 50,000 entries each).
#: Dropped from tool data so a result does not flood the agent's context.
_ANALYSIS_SAMPLE_KEYS = ("thicknesses", "points", "angles")

_RENDER_TIMEOUT_S = 120.0
_ANALYSIS_TIMEOUT_S = 60.0
_LOOKUP_TIMEOUT_S = 15.0


async def _send(
    method: str,
    url: str,
    *,
    headers: dict[str, str],
    timeout: float,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Send one authenticated request and return its JSON object body.

    Raises ``httpx.HTTPError`` for transport and status failures and
    ``ValueError`` when the body is not a JSON object.
    """
    async with httpx.AsyncClient(timeout=timeout) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        else:
            resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("response body is not a JSON object")
    return data


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3g}"
    return str(value)


class GenerateParametricModelTool(BaseTool):
    """Render an existing Yantra4D project (cartridge) with parameter values.

    Calls Yantra4D's render API (``POST /api/render``) with the documented
    payload ``{project, mode?, parameters, export_format}``. Yantra4D renders
    projects it already has; it does not build models from free-form specs,
    and physical settings (material, infill, layer height, nozzle) are not
    generator inputs.
    """

    name = "generate_parametric_model"
    description = (
        "Render an existing Yantra4D project (cartridge) with parameter values and return "
        "the generated parts (part type, artifact URL, size). project_slug must name an "
        "existing project; parameters are the geometry parameters declared in that "
        "project's manifest. Material, infill, layer height and nozzle are not render inputs."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Slug of an existing Yantra4D project.",
                },
                "parameters": {
                    "type": "object",
                    "description": (
                        "Parameter values keyed by the parameter ids in the project's manifest."
                    ),
                },
                "mode": {
                    "type": "string",
                    "description": (
                        "Manifest mode id to render. Yantra4D renders the project's first "
                        "mode when omitted."
                    ),
                },
                "export_format": {
                    "type": "string",
                    "enum": list(YANTRA4D_EXPORT_FORMATS),
                    "default": "stl",
                    "description": "Output format. Yantra4D limits formats by the caller's tier.",
                },
            },
            "required": ["project_slug"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not YANTRA4D_API_URL:
            return ToolResult(success=False, error="YANTRA4D_API_URL not configured")

        project_slug = str(kwargs.get("project_slug") or "").strip()
        if not project_slug:
            return ToolResult(success=False, error="project_slug is required")
        parameters = kwargs.get("parameters")
        if parameters is None:
            parameters = {}
        if not isinstance(parameters, dict):
            return ToolResult(success=False, error="parameters must be an object")
        export_format = str(kwargs.get("export_format") or "stl").strip().lower()
        if export_format not in YANTRA4D_EXPORT_FORMATS:
            return ToolResult(
                success=False,
                error=f"export_format must be one of: {', '.join(YANTRA4D_EXPORT_FORMATS)}",
            )
        mode = str(kwargs.get("mode") or "").strip()

        headers = _service_auth_headers(YANTRA4D_API_TOKEN)
        if not headers:
            return _missing_token("Yantra4D", _YANTRA4D_TOKEN_ENV)

        payload: dict[str, Any] = {
            "project": project_slug,
            "parameters": parameters,
            "export_format": export_format,
        }
        if mode:
            payload["mode"] = mode

        try:
            data = await _send(
                "POST",
                f"{YANTRA4D_API_URL.rstrip('/')}/api/render",
                headers=headers,
                timeout=_RENDER_TIMEOUT_S,
                payload=payload,
            )
        except httpx.HTTPError as exc:
            return ToolResult(
                success=False, error=f"Yantra4D render failed: {_http_error_detail(exc)}"
            )
        except ValueError as exc:
            return ToolResult(success=False, error=f"Yantra4D render failed: {exc}")

        raw_parts = data.get("parts")
        parts = [p for p in raw_parts if isinstance(p, dict)] if isinstance(raw_parts, list) else []
        listing = ", ".join(
            f"{p.get('type', '?')} ({p.get('size_bytes', '?')} bytes)" for p in parts
        )
        output = (
            f"Rendered Yantra4D project '{project_slug}' "
            f"(mode: {mode or 'project default'}, format: {export_format}): "
            f"{len(parts)} part(s){': ' + listing if listing else ''}. "
            "Artifact URLs are in data.parts."
        )
        return ToolResult(success=True, output=output, data=data)


class RunDFMAnalysisTool(BaseTool):
    """Run Yantra4D's wall-thickness and overhang analyses for a project.

    Yantra4D analyses the project's LATEST render on its server, not
    parameters supplied here, so render with ``generate_parametric_model``
    first. Both routes require the ``pro`` tier or above. Results are
    statistics; they do not certify that a part can be manufactured.
    """

    name = "run_dfm_analysis"
    description = (
        "Run Yantra4D's design-for-manufacturability checks (wall thickness and overhang "
        "angles) for an existing project. Yantra4D analyses the project's LATEST render on "
        "its server, not parameters passed here, so render with generate_parametric_model "
        "first. Returns statistics, not a pass/fail certificate."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": "Slug of an existing Yantra4D project that has been rendered.",
                },
                "sample_count": {
                    "type": "integer",
                    "description": "Surface samples per analysis (Yantra4D: 100-50000).",
                    "default": 5000,
                },
                "threshold_deg": {
                    "type": "number",
                    "description": "Overhang angle threshold in degrees (Yantra4D: 20-80).",
                    "default": 45,
                },
            },
            "required": ["project_slug"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not YANTRA4D_API_URL:
            return ToolResult(success=False, error="YANTRA4D_API_URL not configured")

        project_slug = str(kwargs.get("project_slug") or "").strip()
        if not project_slug:
            return ToolResult(success=False, error="project_slug is required")

        thickness_body: dict[str, Any] = {}
        overhang_body: dict[str, Any] = {}
        sample_count = kwargs.get("sample_count")
        if sample_count is not None:
            if isinstance(sample_count, bool) or not isinstance(sample_count, int):
                return ToolResult(success=False, error="sample_count must be an integer")
            thickness_body["sample_count"] = sample_count
            overhang_body["sample_count"] = sample_count
        threshold_deg = kwargs.get("threshold_deg")
        if threshold_deg is not None:
            if isinstance(threshold_deg, bool) or not isinstance(threshold_deg, int | float):
                return ToolResult(success=False, error="threshold_deg must be a number")
            overhang_body["threshold_deg"] = threshold_deg

        headers = _service_auth_headers(YANTRA4D_API_TOKEN)
        if not headers:
            return _missing_token("Yantra4D", _YANTRA4D_TOKEN_ENV)

        base = f"{YANTRA4D_API_URL.rstrip('/')}/api/projects/{quote(project_slug, safe='')}/analyze"
        results: dict[str, Any] = {}
        errors: list[str] = []
        for check, body in (("thickness", thickness_body), ("overhang", overhang_body)):
            try:
                response = await _send(
                    "POST",
                    f"{base}/{check}",
                    headers=headers,
                    timeout=_ANALYSIS_TIMEOUT_S,
                    payload=body,
                )
            except httpx.HTTPError as exc:
                detail = _http_error_detail(exc)
                results[check] = {"error": detail}
                errors.append(f"{check} analysis failed: {detail}")
                continue
            except ValueError as exc:
                results[check] = {"error": str(exc)}
                errors.append(f"{check} analysis failed: {exc}")
                continue
            results[check] = _without_sample_arrays(response)

        note = (
            f"Yantra4D ran these analyses on the latest stored render of '{project_slug}', "
            "not on parameters passed to this tool; that render may come from another "
            "caller. Render with generate_parametric_model first when the parameters matter."
        )
        data = {"project": project_slug, "analyzed": "latest_render", "note": note, **results}
        summary = "; ".join(_summarize(check, results[check]) for check in results)
        output = f"{summary}. {note}"
        if errors:
            return ToolResult(success=False, output=output, error="; ".join(errors), data=data)
        return ToolResult(success=True, output=output, data=data)


def _without_sample_arrays(response: dict[str, Any]) -> dict[str, Any]:
    analysis = response.get("analysis")
    if not isinstance(analysis, dict):
        return response
    omitted = [key for key in _ANALYSIS_SAMPLE_KEYS if key in analysis]
    compact = {key: value for key, value in analysis.items() if key not in omitted}
    if omitted:
        compact["omitted_sample_arrays"] = omitted
    return {**response, "analysis": compact}


def _summarize(check: str, result: dict[str, Any]) -> str:
    if "error" in result:
        return f"{check}: not available ({result['error']})"
    analysis = result.get("analysis")
    if not isinstance(analysis, dict):
        return f"{check}: no analysis returned"
    mesh = result.get("mesh_file", "?")
    if check == "thickness":
        return (
            f"thickness on {mesh}: min {_fmt(analysis.get('min'))}, "
            f"mean {_fmt(analysis.get('mean'))}, "
            f"thin walls {_fmt(analysis.get('thin_wall_count'))} "
            f"of {_fmt(analysis.get('sample_count'))} samples"
        )
    return (
        f"overhang on {mesh}: {_fmt(analysis.get('overhang_count'))} "
        f"of {_fmt(analysis.get('sample_count'))} samples beyond "
        f"{_fmt(analysis.get('threshold_deg'))} degrees"
    )


class GenerateQuoteTool(BaseTool):
    """Generate a fabrication quote using the Yantra/Cotiza quote contract."""

    name = "generate_quote"
    description = (
        "Generate a fabrication price quote for a 3D model. "
        "Uses Cotiza/Forgesight pricing intelligence for accurate estimates."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "project_slug": {
                    "type": "string",
                    "description": (
                        "Yantra4D project slug. When provided, Selva requests the "
                        "quote through Yantra4D's project endpoint."
                    ),
                },
                "geometry": {
                    "type": "object",
                    "description": (
                        "Structured geometry data required by Cotiza when no "
                        "project_slug is available."
                    ),
                },
                "project": {
                    "type": "object",
                    "description": (
                        "Structured project metadata required by Cotiza when no "
                        "project_slug is available."
                    ),
                },
                "model_id": {
                    "type": "string",
                    "description": "Optional Yantra4D model ID for traceability",
                },
                "material": {"type": "string", "default": "PLA"},
                "quantity": {"type": "integer", "default": 1, "description": "Number of units"},
                "process": {"type": "string", "default": "fdm"},
                "priority": {
                    "type": "string",
                    "enum": ["standard", "express", "rush"],
                    "default": "standard",
                },
                "finish": {"type": "string", "default": "standard"},
                "currency": {"type": "string", "default": "MXN"},
                "notes": {"type": "string", "default": ""},
                "require_market_verified": {
                    "type": "boolean",
                    "default": True,
                    "description": "Require Cotiza/Forgesight market-verified pricing.",
                },
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        project_slug = str(kwargs.get("project_slug") or "").strip()
        require_market_verified = bool(kwargs.get("require_market_verified", True))

        quote_context = {
            "material": kwargs.get("material", "PLA"),
            "quantity": kwargs.get("quantity", 1),
            "process": kwargs.get("process", "fdm"),
            "priority": kwargs.get("priority", "standard"),
            "finish": kwargs.get("finish", "standard"),
            "currency": kwargs.get("currency", "MXN"),
            "notes": kwargs.get("notes", ""),
            "require_market_verified": require_market_verified,
        }
        if kwargs.get("model_id"):
            quote_context["model_id"] = kwargs["model_id"]

        if project_slug:
            if not YANTRA4D_API_URL:
                return ToolResult(success=False, error="YANTRA4D_API_URL not configured")
            api_url = YANTRA4D_API_URL.rstrip("/")
            endpoint = f"{api_url}/api/projects/{quote(project_slug, safe='')}/cotiza-quote-request"
            payload = quote_context
        else:
            if not COTIZA_API_URL:
                return ToolResult(success=False, error="COTIZA_API_URL not configured")
            geometry = kwargs.get("geometry")
            project = kwargs.get("project")
            if not isinstance(geometry, dict) or not geometry:
                return ToolResult(
                    success=False,
                    error="geometry is required for Cotiza quote requests without project_slug",
                )
            if not isinstance(project, dict) or not project:
                return ToolResult(
                    success=False,
                    error="project is required for Cotiza quote requests without project_slug",
                )
            api_url = COTIZA_API_URL.rstrip("/")
            # Served path: the Nest controller is quotes + from-yantra4d and Cotiza
            # sets no global prefix (see tests/fixtures/phygital_routes.json).
            endpoint = f"{api_url}/quotes/from-yantra4d"
            process_map = {
                "fdm": "3d_fff",
                "fff": "3d_fff",
                "3d_fff": "3d_fff",
                "sla": "3d_sla",
                "3d_sla": "3d_sla",
                "cnc": "cnc_3axis",
                "cnc_3axis": "cnc_3axis",
                "laser": "laser_2d",
                "laser_2d": "laser_2d",
            }
            raw_process = str(kwargs.get("process", "fdm")).lower()
            cotiza_process = process_map.get(raw_process, "3d_fff")
            project_name = str(project.get("name") or project.get("slug") or "Yantra4D project")
            payload = {
                "source": "yantra4d",
                "project": project,
                "geometry": geometry,
                "item": {
                    "name": project_name,
                    "process": cotiza_process,
                    "material": quote_context["material"],
                    "quantity": quote_context["quantity"],
                    "finish": quote_context["finish"],
                    "options": {
                        "priority": quote_context["priority"],
                        "require_market_verified": require_market_verified,
                    },
                },
                "currency": quote_context["currency"],
                "notes": quote_context["notes"],
                "require_market_verified": require_market_verified,
            }

        if project_slug:
            headers = _service_auth_headers(YANTRA4D_API_TOKEN)
            if not headers:
                return _missing_token("Yantra4D", _YANTRA4D_TOKEN_ENV)
        else:
            headers = _service_auth_headers(COTIZA_API_TOKEN)
            if not headers:
                return _missing_token("Cotiza", _COTIZA_TOKEN_ENV)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return ToolResult(
                success=False, error=f"Quote generation failed: {_http_error_detail(exc)}"
            )

        price = data.get("totalPrice", data.get("total_price", data.get("total")))
        currency = data.get("currency", "MXN")
        quote_id = data.get("quoteId", data.get("quote_id", data.get("id", "pending")))
        market_verified = bool(
            data.get("market_verified")
            or (data.get("market_context") or {}).get("market_verified")
            or (data.get("cotiza_quote") or {}).get("market_verified")
        )
        if require_market_verified and not market_verified:
            return ToolResult(
                success=False,
                error="Quote was created/submitted but is not market verified",
                data=data,
            )
        if price is None:
            output = f"Quote request submitted: {quote_id}"
        else:
            output = (
                f"Quote generated: {currency} ${float(price):.2f} "
                f"for {kwargs.get('quantity', 1)} unit(s)"
            )
        return ToolResult(
            success=True,
            output=output,
            data=data,
        )


class GetProductionOrderStatusTool(BaseTool):
    """Read a Pravara-MES production order (read-only).

    Selva does not create production orders: Cotiza prices, Dhanam bills and
    Pravara executes. An order reaches Pravara when a person orders a Cotiza
    quote, through Cotiza's signed dispatch. This tool only calls
    ``GET /v1/orders/:id``, which Pravara serves to service tokens holding
    ``pravara-mes:read`` or ``pravara-mes:jobs``.

    PLATFORM audience: the lookup uses Selva's own Pravara service identity,
    so tenant swarms must not read through it.
    """

    name = "get_production_order_status"
    description = (
        "Read the status of a Pravara-MES production order by its order ID (UUID). "
        "Read-only. Selva cannot create production orders: they are created when a "
        "person orders a Cotiza quote, and Cotiza dispatches the order to Pravara-MES."
    )
    audience = Audience.PLATFORM

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "Pravara-MES production order ID (UUID).",
                },
            },
            "required": ["order_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not PRAVARA_MES_API_URL:
            return ToolResult(success=False, error="PRAVARA_MES_API_URL not configured")

        try:
            order_id = str(uuid.UUID(str(kwargs.get("order_id") or "").strip()))
        except ValueError:
            return ToolResult(success=False, error="order_id must be a Pravara order UUID")

        headers = _service_auth_headers(PRAVARA_MES_API_TOKEN)
        if not headers:
            return _missing_token("Pravara-MES", _PRAVARA_TOKEN_ENV)

        try:
            data = await _send(
                "GET",
                f"{PRAVARA_MES_API_URL.rstrip('/')}/v1/orders/{order_id}",
                headers=headers,
                timeout=_LOOKUP_TIMEOUT_S,
            )
        except httpx.HTTPError as exc:
            return ToolResult(
                success=False,
                error=f"Pravara order lookup failed: {_http_error_detail(exc)}",
            )
        except ValueError as exc:
            return ToolResult(success=False, error=f"Pravara order lookup failed: {exc}")

        return ToolResult(
            success=True,
            output=f"Pravara production order {order_id}: status {data.get('status', 'unknown')}.",
            data=data,
        )
