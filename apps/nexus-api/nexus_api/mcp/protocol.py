"""MCP over Streamable HTTP, the stateless subset: one JSON-RPC 2.0 message per POST.

A minimal handler rather than the official ``mcp`` SDK, which is not a
dependency of nexus-api; the tools need only ``initialize``, ``ping``,
``tools/list`` and ``tools/call`` (the same shape as the other MADFAM
platforms' native MCPs). Bytes and a context in, an ``Exchange`` (HTTP status,
body, audit fields) out; no FastAPI here.

* A request (has ``id``) gets one JSON-RPC response (HTTP 200, or 400 for a
  message that is not JSON-RPC at all).
* A notification or a client response (no ``id``) gets HTTP 202, no body.
* Batches (JSON arrays) are refused: MCP removed them in 2025-06-18.
* No ``Mcp-Session-Id`` is issued; every request stands alone.
* Unknown tool → JSON-RPC ``-32602``; bad arguments or a failing tool → a tool
  result with ``isError: true`` (the model can read and correct it).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from .registry import ToolContext, ToolError, ToolSpec, validate_arguments

logger = logging.getLogger(__name__)

#: Newest first; ``initialize`` answers the client's version when listed here.
SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")
LATEST_VERSION = SUPPORTED_VERSIONS[0]
SERVER_INFO = {"name": "selva", "title": "Selva — inference usage (read-only)", "version": "0.1.0"}
INSTRUCTIONS = (
    "Read-only inference-usage tools for MADFAM's cost ledger (RFC 0051). Dollar figures "
    "are LIST-PRICE ESTIMATES in USD from a public price table: not cash, not COGS, never "
    "converted. Funding is unattributed. Periods are civil months in America/Mexico_City "
    "(YYYY-MM). Unknown values are null, never 0. Every answer is scoped to the "
    "organization your machine client is bound to; there are no write tools."
)
#: Requests are tiny; anything larger is refused before parsing.
MAX_BODY_BYTES = 64 * 1024

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602


@dataclass
class Exchange:
    status: int
    body: dict[str, Any] | None
    method: str = ""
    tool: str = ""
    #: ok | tool_error | invalid_arguments | unknown_tool | internal_error (tools/call only)
    outcome: str = ""
    args_sha256: str = ""


def args_sha256(arguments: Any) -> str:
    canonical = json.dumps(arguments, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _error(request_id: Any, code: int, message: str, status: int = 200, **audit: str) -> Exchange:
    body = {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    return Exchange(status=status, body=body, **audit)


def _result(request_id: Any, result: dict[str, Any], **audit: str) -> Exchange:
    return Exchange(
        status=200, body={"jsonrpc": "2.0", "id": request_id, "result": result}, **audit
    )


def _tool_result(structured: dict[str, Any]) -> dict[str, Any]:
    text = json.dumps(structured, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
        "isError": False,
    }


def _tool_failure(code: str, message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": f"{code}: {message}"}], "isError": True}


def _initialize(request_id: Any, params: Any) -> Exchange:
    asked = params.get("protocolVersion") if isinstance(params, dict) else None
    version = asked if asked in SUPPORTED_VERSIONS else LATEST_VERSION
    return _result(
        request_id,
        {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": INSTRUCTIONS,
        },
        method="initialize",
    )


async def _call_tool(
    request_id: Any, params: Any, context: ToolContext, tools: dict[str, ToolSpec]
) -> Exchange:
    if not isinstance(params, dict) or not isinstance(params.get("name"), str):
        return _error(request_id, INVALID_PARAMS, "params.name is required", method="tools/call")
    name = params["name"]
    arguments = params.get("arguments")
    arguments = {} if arguments is None else arguments
    audit = {"method": "tools/call", "tool": name, "args_sha256": args_sha256(arguments)}
    spec = tools.get(name)
    if spec is None:
        return _error(
            request_id,
            INVALID_PARAMS,
            f"Unknown tool: {name[:64]}",
            outcome="unknown_tool",
            **audit,
        )
    problems = validate_arguments(spec.input_schema, arguments)
    if problems:
        failure = _tool_failure("invalid_arguments", "; ".join(problems))
        return _result(request_id, failure, outcome="invalid_arguments", **audit)
    try:
        structured = await spec.handler(context, arguments)
    except ToolError as exc:
        return _result(
            request_id, _tool_failure(exc.code, exc.message), outcome="tool_error", **audit
        )
    except Exception as exc:  # never the traceback: it could carry tenant data
        logger.error("MCP tool %s failed (%s)", name, type(exc).__name__)
        failure = _tool_failure("internal_error", "the tool failed; nothing was changed")
        return _result(request_id, failure, outcome="internal_error", **audit)
    return _result(request_id, _tool_result(structured), outcome="ok", **audit)


async def handle(raw: bytes, context: ToolContext, tools: dict[str, ToolSpec]) -> Exchange:
    """One HTTP POST body → its answer."""
    if len(raw) > MAX_BODY_BYTES:
        return _error(None, INVALID_REQUEST, "Request too large", status=413)
    try:
        message = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _error(None, PARSE_ERROR, "Parse error", status=400)
    if isinstance(message, list):
        return _error(None, INVALID_REQUEST, "Batches are not supported", status=400)
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return _error(None, INVALID_REQUEST, "Not a JSON-RPC 2.0 message", status=400)
    if "id" not in message:  # a notification, or the client answering us
        return Exchange(status=202, body=None, method=str(message.get("method", "")))
    request_id = message["id"]
    if isinstance(request_id, bool) or not isinstance(request_id, str | int):
        return _error(None, INVALID_REQUEST, "id must be a string or an integer", status=400)
    method = message.get("method")
    if not isinstance(method, str):
        return _error(request_id, INVALID_REQUEST, "method is required", status=400)
    params = message.get("params") or {}
    if method == "initialize":
        return _initialize(request_id, params)
    if method == "ping":
        return _result(request_id, {}, method=method)
    if method == "tools/list":
        listing = [spec.listing() for spec in tools.values()]
        return _result(request_id, {"tools": listing}, method=method)
    if method == "tools/call":
        return await _call_tool(request_id, params, context, tools)
    return _error(request_id, METHOD_NOT_FOUND, f"Method not found: {method[:64]}", method=method)
