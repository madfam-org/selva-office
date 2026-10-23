"""MCP application errors must survive the remote-tool adapter boundary."""

from unittest.mock import AsyncMock

import pytest

from selva_tools.mcp.client import McpToolAdapter, McpTransport


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload, expected_success",
    [
        ({"content": [{"type": "text", "text": "checked"}]}, True),
        ({"content": [], "structuredContent": {"count": 0}, "isError": False}, True),
        ({"content": [{"type": "text", "text": "not authorized"}], "isError": True}, False),
        ({"content": [], "isError": True}, False),
        ({"content": [], "isError": "false"}, False),
        ({"content": [{"type": "text", "text": {"error": "invalid"}}]}, False),
        ({"content": ["not a content block"]}, False),
        ({"content": "not a content array"}, False),
        ("not a result object", False),
        ({}, False),
    ],
)
async def test_remote_result_contract(payload, expected_success) -> None:
    transport = AsyncMock(spec=McpTransport)
    transport.call_tool.return_value = payload
    tool = McpToolAdapter("synthetic_check", "Synthetic check", {"type": "object"}, transport)
    result = await tool.execute()
    assert result.success is expected_success
    if not expected_success:
        assert result.error
    if isinstance(payload, dict) and payload.get("isError") is True:
        assert result.data == payload
    transport.call_tool.assert_awaited_once_with("synthetic_check", {})


@pytest.mark.asyncio
async def test_transport_error_is_redacted(caplog) -> None:
    transport = AsyncMock(spec=McpTransport)
    transport.call_tool.side_effect = RuntimeError("SENSITIVE_SENTINEL")
    tool = McpToolAdapter("synthetic_check", "Synthetic check", {"type": "object"}, transport)
    result = await tool.execute()
    assert result.success is False
    assert result.error == "MCP transport unavailable"
    assert "SENSITIVE_SENTINEL" not in result.model_dump_json() + caplog.text
