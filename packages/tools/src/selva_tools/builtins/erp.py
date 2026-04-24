"""ERP export tools -- CONTPAQi and generic ERP data export."""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class CONTPAQiExportTool(BaseTool):
    name = "contpaqi_export"
    description = (
        "Generate CONTPAQi-compatible CSV or XML from accounting data (polizas, auxiliares)"
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": (
                        "Accounting data with keys like 'polizas' (array of "
                        "journal entries) and 'auxiliares' (array of auxiliary "
                        "ledger records)"
                    ),
                },
                "output_format": {
                    "type": "string",
                    "enum": ["csv", "xml"],
                    "default": "csv",
                    "description": "Export format: csv or xml",
                },
            },
            "required": ["data"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        data: dict[str, Any] = kwargs.get("data", {})
        output_format: str = kwargs.get("output_format", "csv")

        if not data:
            return ToolResult(success=False, error="data is required")

        polizas = data.get("polizas", [])
        auxiliares = data.get("auxiliares", [])

        if not polizas and not auxiliares:
            return ToolResult(
                success=False,
                error="data must contain 'polizas' and/or 'auxiliares' arrays",
            )

        try:
            if output_format == "xml":
                content = _build_contpaqi_xml(polizas, auxiliares)
            else:
                content = _build_contpaqi_csv(polizas, auxiliares)

            return ToolResult(
                success=True,
                output=(
                    f"CONTPAQi {output_format.upper()} export generated: "
                    f"{len(polizas)} poliza(s), {len(auxiliares)} auxiliar(es)"
                ),
                data={
                    "content": content,
                    "format": output_format,
                    "polizas_count": len(polizas),
                    "auxiliares_count": len(auxiliares),
                },
            )
        except Exception as exc:
            logger.error("CONTPAQi export failed: %s", exc)
            return ToolResult(success=False, error=str(exc))


def _build_contpaqi_csv(
    polizas: list[dict[str, Any]],
    auxiliares: list[dict[str, Any]],
) -> str:
    """Build a CONTPAQi-compatible CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)

    if polizas:
        # Header row for polizas
        writer.writerow(
            [
                "tipo_poliza",
                "numero",
                "fecha",
                "concepto",
                "cuenta",
                "debe",
                "haber",
                "referencia",
            ]
        )
        for p in polizas:
            writer.writerow(
                [
                    p.get("tipo_poliza", "D"),
                    p.get("numero", ""),
                    p.get("fecha", ""),
                    p.get("concepto", ""),
                    p.get("cuenta", ""),
                    p.get("debe", "0.00"),
                    p.get("haber", "0.00"),
                    p.get("referencia", ""),
                ]
            )

    if auxiliares:
        if polizas:
            writer.writerow([])  # Separator
        writer.writerow(
            [
                "cuenta",
                "nombre_cuenta",
                "fecha",
                "tipo_movimiento",
                "debe",
                "haber",
                "saldo",
                "referencia",
            ]
        )
        for a in auxiliares:
            writer.writerow(
                [
                    a.get("cuenta", ""),
                    a.get("nombre_cuenta", ""),
                    a.get("fecha", ""),
                    a.get("tipo_movimiento", ""),
                    a.get("debe", "0.00"),
                    a.get("haber", "0.00"),
                    a.get("saldo", "0.00"),
                    a.get("referencia", ""),
                ]
            )

    return output.getvalue()


def _build_contpaqi_xml(
    polizas: list[dict[str, Any]],
    auxiliares: list[dict[str, Any]],
) -> str:
    """Build a CONTPAQi-compatible XML string."""
    lines: list[str] = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<ContpaqiExport version="1.0">')

    if polizas:
        lines.append("  <Polizas>")
        for p in polizas:
            lines.append("    <Poliza")
            for key in (
                "tipo_poliza",
                "numero",
                "fecha",
                "concepto",
                "cuenta",
                "debe",
                "haber",
                "referencia",
            ):
                val = str(p.get(key, "")).replace("&", "&amp;").replace('"', "&quot;")
                lines.append(f'      {key}="{val}"')
            lines.append("    />")
        lines.append("  </Polizas>")

    if auxiliares:
        lines.append("  <Auxiliares>")
        for a in auxiliares:
            lines.append("    <Auxiliar")
            for key in (
                "cuenta",
                "nombre_cuenta",
                "fecha",
                "tipo_movimiento",
                "debe",
                "haber",
                "saldo",
                "referencia",
            ):
                val = str(a.get(key, "")).replace("&", "&amp;").replace('"', "&quot;")
                lines.append(f'      {key}="{val}"')
            lines.append("    />")
        lines.append("  </Auxiliares>")

    lines.append("</ContpaqiExport>")
    return "\n".join(lines)


class GenericERPExportTool(BaseTool):
    name = "erp_export"
    description = "Generic JSON/CSV export for any ERP system with optional field mapping schema"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "data": {
                    "type": "object",
                    "description": "Data to export (dict or list of records)",
                },
                "format": {
                    "type": "string",
                    "enum": ["json", "csv"],
                    "default": "json",
                    "description": "Output format",
                },
                "schema": {
                    "type": "object",
                    "description": (
                        "Optional field mapping: {source_field: target_field}. "
                        "Renames fields in the output."
                    ),
                },
            },
            "required": ["data"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        data: Any = kwargs.get("data", {})
        fmt: str = kwargs.get("format", "json")
        schema_map: dict[str, str] | None = kwargs.get("schema")

        if not data:
            return ToolResult(success=False, error="data is required")

        # Normalize data to a list of records
        records: list[dict[str, Any]]
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # If the dict has a single key with a list value, unwrap it
            values = list(data.values())
            records = values[0] if len(values) == 1 and isinstance(values[0], list) else [data]
        else:
            return ToolResult(
                success=False,
                error="data must be a dict or array of records",
            )

        # Apply schema mapping
        if schema_map:
            mapped_records: list[dict[str, Any]] = []
            for record in records:
                mapped: dict[str, Any] = {}
                for src_key, value in record.items():
                    target_key = schema_map.get(src_key, src_key)
                    mapped[target_key] = value
                mapped_records.append(mapped)
            records = mapped_records

        try:
            if fmt == "csv":
                content = _records_to_csv(records)
            else:
                content = json.dumps(records, ensure_ascii=False, indent=2, default=str)

            return ToolResult(
                success=True,
                output=f"ERP export ({fmt.upper()}): {len(records)} record(s)",
                data={
                    "content": content,
                    "format": fmt,
                    "record_count": len(records),
                },
            )
        except Exception as exc:
            logger.error("ERP export failed: %s", exc)
            return ToolResult(success=False, error=str(exc))


def _records_to_csv(records: list[dict[str, Any]]) -> str:
    """Convert a list of dicts to a CSV string."""
    if not records:
        return ""

    output = io.StringIO()
    # Collect all unique keys for headers
    all_keys: list[str] = []
    seen: set[str] = set()
    for record in records:
        for key in record:
            if key not in seen:
                all_keys.append(key)
                seen.add(key)

    writer = csv.DictWriter(output, fieldnames=all_keys, extrasaction="ignore")
    writer.writeheader()
    for record in records:
        writer.writerow(record)

    return output.getvalue()
