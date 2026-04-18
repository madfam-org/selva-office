"""Phygital Node tools — parametric design, DFM analysis, and manufacturing.

Implements Axiom III of the Swarm Governing Manifesto:
"We do not extrude until the digital twin has succeeded."

These tools bridge the digital-to-physical gap:
- Generate parametric 3D models via Yantra4D
- Run Design for Manufacturability analysis
- Generate fabrication quotes via Cotiza/Forgesight
- Create manufacturing work orders via Pravara-MES
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

YANTRA4D_API_URL = os.environ.get("YANTRA4D_API_URL", "")
PRAVARA_MES_API_URL = os.environ.get("PRAVARA_MES_API_URL", "")
COTIZA_API_URL = os.environ.get("COTIZA_API_URL", "")


class GenerateParametricModelTool(BaseTool):
    """Generate a parametric 3D model via Yantra4D.

    Takes geometric parameters and material specs, returns a model ID
    that can be passed to DFM analysis and quote generation.
    """

    name = "generate_parametric_model"
    description = (
        "Generate a parametric 3D model from specifications via Yantra4D. "
        "Returns a model ID for DFM analysis and manufacturing. "
        "Use when you need to create a 3D design from parameters."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Model name/identifier"},
                "geometry_type": {
                    "type": "string",
                    "description": "Base geometry (box, cylinder, sphere, custom)",
                    "default": "custom",
                },
                "dimensions": {
                    "type": "object",
                    "description": "Dimension parameters (e.g., {width: 100, height: 50, depth: 30} in mm)",
                },
                "material": {
                    "type": "string",
                    "description": "Material (PLA, ABS, PETG, Nylon-CF, PEEK, TPU)",
                    "default": "PLA",
                },
                "infill_percent": {
                    "type": "integer",
                    "description": "Infill density percentage (0-100)",
                    "default": 20,
                },
            },
            "required": ["name", "dimensions"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not YANTRA4D_API_URL:
            return ToolResult(success=False, error="YANTRA4D_API_URL not configured")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{YANTRA4D_API_URL}/api/v1/models/generate",
                    json={
                        "name": kwargs.get("name", ""),
                        "geometry_type": kwargs.get("geometry_type", "custom"),
                        "dimensions": kwargs.get("dimensions", {}),
                        "material": kwargs.get("material", "PLA"),
                        "infill_percent": kwargs.get("infill_percent", 20),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            model_id = data.get("model_id", data.get("id", "unknown"))
            return ToolResult(
                success=True,
                output=f"Parametric model generated: {model_id} ({kwargs.get('name', '')})",
                data=data,
            )
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Model generation failed: {exc}")


class RunDFMAnalysisTool(BaseTool):
    """Run Design for Manufacturability analysis on a 3D model.

    Checks if a model can be successfully fabricated with the specified
    material and process. Implements Axiom III: digital twin must succeed
    before physical extrusion.
    """

    name = "run_dfm_analysis"
    description = (
        "Analyze a 3D model for manufacturability (DFM). "
        "Checks wall thickness, overhangs, support requirements, and material compatibility. "
        "The model MUST pass DFM before fabrication can proceed (Axiom III)."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "ID of the model to analyze"},
                "process": {
                    "type": "string",
                    "description": "Manufacturing process (fdm, sla, sls, cnc)",
                    "default": "fdm",
                },
                "material": {
                    "type": "string",
                    "description": "Target material",
                    "default": "PLA",
                },
            },
            "required": ["model_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not YANTRA4D_API_URL:
            return ToolResult(success=False, error="YANTRA4D_API_URL not configured")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{YANTRA4D_API_URL}/api/v1/models/{kwargs['model_id']}/dfm",
                    json={
                        "process": kwargs.get("process", "fdm"),
                        "material": kwargs.get("material", "PLA"),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            passed = data.get("passed", False)
            issues = data.get("issues", [])
            status = "PASSED" if passed else f"FAILED ({len(issues)} issues)"

            return ToolResult(
                success=True,
                output=f"DFM Analysis: {status}. {'; '.join(issues[:3]) if issues else 'No issues found.'}",
                data=data,
            )
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"DFM analysis failed: {exc}")


class GenerateQuoteTool(BaseTool):
    """Generate a fabrication quote from model specs and pricing intelligence."""

    name = "generate_quote"
    description = (
        "Generate a fabrication price quote for a 3D model. "
        "Uses Cotiza/Forgesight pricing intelligence for accurate estimates."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID from Yantra4D"},
                "material": {"type": "string", "default": "PLA"},
                "quantity": {"type": "integer", "default": 1, "description": "Number of units"},
                "process": {"type": "string", "default": "fdm"},
                "priority": {
                    "type": "string",
                    "enum": ["standard", "express", "rush"],
                    "default": "standard",
                },
            },
            "required": ["model_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        api_url = COTIZA_API_URL or YANTRA4D_API_URL
        if not api_url:
            return ToolResult(success=False, error="No quoting service configured")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{api_url}/api/v1/quotes/generate",
                    json={
                        "model_id": kwargs.get("model_id", ""),
                        "material": kwargs.get("material", "PLA"),
                        "quantity": kwargs.get("quantity", 1),
                        "process": kwargs.get("process", "fdm"),
                        "priority": kwargs.get("priority", "standard"),
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            price = data.get("total_price", data.get("price", 0))
            currency = data.get("currency", "MXN")
            return ToolResult(
                success=True,
                output=f"Quote generated: {currency} ${price:.2f} for {kwargs.get('quantity', 1)} unit(s)",
                data=data,
            )
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Quote generation failed: {exc}")


class CreateWorkOrderTool(BaseTool):
    """Create a manufacturing work order in Pravara-MES.

    This is the physical execution step. Per Axiom III, this should ONLY
    be called after DFM analysis passes. The phygital graph enforces this
    with a mandatory HITL review gate before work order creation.
    """

    name = "create_work_order"
    description = (
        "Create a manufacturing work order in the MES. "
        "IMPORTANT: Only use after DFM analysis has passed. "
        "This triggers actual physical fabrication."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "model_id": {"type": "string", "description": "Model ID (must have passed DFM)"},
                "quantity": {"type": "integer", "default": 1},
                "material": {"type": "string", "default": "PLA"},
                "priority": {
                    "type": "string",
                    "enum": ["low", "normal", "high", "urgent"],
                    "default": "normal",
                },
                "notes": {"type": "string", "default": ""},
            },
            "required": ["model_id"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        if not PRAVARA_MES_API_URL:
            return ToolResult(success=False, error="PRAVARA_MES_API_URL not configured")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{PRAVARA_MES_API_URL}/api/v1/work-orders",
                    json={
                        "model_id": kwargs.get("model_id", ""),
                        "quantity": kwargs.get("quantity", 1),
                        "material": kwargs.get("material", "PLA"),
                        "priority": kwargs.get("priority", "normal"),
                        "notes": kwargs.get("notes", ""),
                        "source": "selva-agent",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            order_id = data.get("work_order_id", data.get("id", "unknown"))
            return ToolResult(
                success=True,
                output=f"Work order created: {order_id} (qty: {kwargs.get('quantity', 1)}, material: {kwargs.get('material', 'PLA')})",
                data=data,
            )
        except httpx.HTTPError as exc:
            return ToolResult(success=False, error=f"Work order creation failed: {exc}")
