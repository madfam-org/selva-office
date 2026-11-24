"""Tool specifications, the caller's context and the argument check.

Hand-written tools, each with a typed ``inputSchema`` and an ``outputSchema``.
The output schema of a tool that serves an HTTP read IS that read's response
model (``model_json_schema()``), so the tool and the route cannot drift; the
tests validate every tool's real output against it.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolContext:
    """Who is calling: the org and the machine client from the verified token, never arguments."""

    org_id: str
    client_id: str


class ToolError(Exception):
    """A failure the caller can act on: a stable code and a plain message (no data)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


ToolHandler = Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    #: The RFC 0051 catalog name (``inference.usage``). ``name`` uses ``_``
    #: because MCP clients such as Claude accept only ``[A-Za-z0-9_-]``.
    title: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    handler: ToolHandler = field(compare=False)

    def listing(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
            "outputSchema": self.output_schema,
            "annotations": {
                "title": self.title,
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        }


def object_schema(
    properties: dict[str, Any] | None = None, required: tuple[str, ...] = ()
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties or {},
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


def validate_arguments(schema: dict[str, Any], arguments: Any) -> list[str]:
    """Problems with ``arguments`` against the JSON Schema subset the tools use.

    Supported: an object of string properties (``pattern``, ``maxLength``),
    ``required``, no extra properties. Messages name the argument and never
    echo its value.
    """
    if not isinstance(arguments, dict):
        return ["arguments: must be an object"]
    properties = schema.get("properties", {})
    problems = [f"{name}: required" for name in schema.get("required", ()) if name not in arguments]
    for name, value in arguments.items():
        spec = properties.get(name)
        if spec is None:
            problems.append(f"{name}: unknown argument")
            continue
        if spec.get("type") == "string":
            if not isinstance(value, str):
                problems.append(f"{name}: must be a string")
            elif len(value) > spec.get("maxLength", len(value)):
                problems.append(f"{name}: too long")
            elif "pattern" in spec and not re.fullmatch(spec["pattern"], value):
                problems.append(f"{name}: does not match {spec['pattern']}")
    return sorted(problems)
