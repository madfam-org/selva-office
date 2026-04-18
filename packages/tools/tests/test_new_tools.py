"""Tests for the 14 new built-in tools added in Wave 5.

Tests cover:
- Tool registration in get_builtin_tools()
- Valid name and description on each tool class
- Valid parameters_schema() returning {"type": "object", ...}
- Instantiation without error

These are registration/metadata tests -- no mocking or network calls needed.
"""

from __future__ import annotations

import pytest

from selva_tools.builtins import get_builtin_tools
from selva_tools.builtins.calendar_tools import (
    CreateCalendarEventTool,
    ListCalendarEventsTool,
)
from selva_tools.builtins.database_tools import (
    DatabaseSchemaTool,
    SQLQueryTool,
    SQLWriteTool,
)
from selva_tools.builtins.document_tools import (
    GenerateChartTool,
    GeneratePDFTool,
    MarkdownToHTMLTool,
    ParsePDFTool,
)
from selva_tools.builtins.email_tools import ReadEmailTool, SendEmailTool
from selva_tools.builtins.http_tools import (
    GraphQLQueryTool,
    HTTPRequestTool,
    WebhookSendTool,
)

# ---------------------------------------------------------------------------
# Total tool count
# ---------------------------------------------------------------------------

def test_tool_count_at_least_53() -> None:
    """39 existing + 14 new = 53 minimum (may be higher with A2A tool)."""
    tools = get_builtin_tools()
    assert len(tools) >= 53, f"Expected >= 53 tools, got {len(tools)}"


# ---------------------------------------------------------------------------
# Registration: each new tool name must appear in get_builtin_tools()
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", [
    "send_email",
    "read_email",
    "create_calendar_event",
    "list_calendar_events",
    "sql_query",
    "sql_write",
    "database_schema",
    "http_request",
    "graphql_query",
    "webhook_send",
    "generate_pdf",
    "parse_pdf",
    "markdown_to_html",
    "generate_chart",
])
def test_tool_registered(name: str) -> None:
    tools = {t.name: t for t in get_builtin_tools()}
    assert name in tools, f"Tool '{name}' not found in get_builtin_tools()"
    schema = tools[name].parameters_schema()
    assert schema["type"] == "object", f"Tool '{name}' schema type is not 'object'"
    assert "properties" in schema, f"Tool '{name}' schema has no 'properties'"


# ---------------------------------------------------------------------------
# Class-level metadata tests
# ---------------------------------------------------------------------------

ALL_NEW_TOOL_CLASSES = [
    SendEmailTool,
    ReadEmailTool,
    CreateCalendarEventTool,
    ListCalendarEventsTool,
    SQLQueryTool,
    SQLWriteTool,
    DatabaseSchemaTool,
    HTTPRequestTool,
    GraphQLQueryTool,
    WebhookSendTool,
    GeneratePDFTool,
    ParsePDFTool,
    MarkdownToHTMLTool,
    GenerateChartTool,
]


@pytest.mark.parametrize("tool_cls", ALL_NEW_TOOL_CLASSES, ids=lambda c: c.name)
def test_tool_has_name_and_description(tool_cls: type) -> None:
    assert hasattr(tool_cls, "name"), f"{tool_cls.__name__} missing 'name'"
    assert hasattr(tool_cls, "description"), f"{tool_cls.__name__} missing 'description'"
    assert len(tool_cls.name) > 0, f"{tool_cls.__name__}.name is empty"
    assert len(tool_cls.description) > 0, f"{tool_cls.__name__}.description is empty"


@pytest.mark.parametrize("tool_cls", ALL_NEW_TOOL_CLASSES, ids=lambda c: c.name)
def test_tool_instantiation(tool_cls: type) -> None:
    instance = tool_cls()
    assert instance is not None
    assert instance.name == tool_cls.name


@pytest.mark.parametrize("tool_cls", ALL_NEW_TOOL_CLASSES, ids=lambda c: c.name)
def test_tool_schema_structure(tool_cls: type) -> None:
    instance = tool_cls()
    schema = instance.parameters_schema()
    assert isinstance(schema, dict)
    assert schema["type"] == "object"
    assert "properties" in schema
    assert isinstance(schema["properties"], dict)


@pytest.mark.parametrize("tool_cls", ALL_NEW_TOOL_CLASSES, ids=lambda c: c.name)
def test_tool_openai_spec(tool_cls: type) -> None:
    instance = tool_cls()
    spec = instance.to_openai_spec()
    assert spec["type"] == "function"
    assert spec["function"]["name"] == instance.name
    assert spec["function"]["description"] == instance.description
    assert spec["function"]["parameters"]["type"] == "object"


# ---------------------------------------------------------------------------
# SSRF validation tests (http_tools._validate_url)
# ---------------------------------------------------------------------------

class TestSSRFValidation:
    def test_valid_public_url(self) -> None:
        from selva_tools.builtins.http_tools import _validate_url

        # Should not raise for a public URL
        result = _validate_url("https://example.com/api")
        assert result == "https://example.com/api"

    def test_rejects_private_ip(self) -> None:
        from selva_tools.builtins.http_tools import _validate_url

        with pytest.raises(ValueError, match="private/reserved"):
            _validate_url("http://127.0.0.1:8080/api")

    def test_rejects_ftp_scheme(self) -> None:
        from selva_tools.builtins.http_tools import _validate_url

        with pytest.raises(ValueError, match="scheme must be http or https"):
            _validate_url("ftp://example.com/file")

    def test_rejects_long_url(self) -> None:
        from selva_tools.builtins.http_tools import _validate_url

        with pytest.raises(ValueError, match="maximum length"):
            _validate_url("https://example.com/" + "a" * 2100)

    def test_rejects_missing_hostname(self) -> None:
        from selva_tools.builtins.http_tools import _validate_url

        with pytest.raises(ValueError, match="missing a hostname"):
            _validate_url("https://")


# ---------------------------------------------------------------------------
# SQL security tests (database_tools query validation)
# ---------------------------------------------------------------------------

class TestSQLSecurity:
    @pytest.mark.asyncio
    async def test_sql_query_rejects_insert(self) -> None:
        tool = SQLQueryTool()
        result = await tool.execute(query="INSERT INTO users VALUES (1, 'test')")
        assert not result.success
        assert "sql_write" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sql_query_rejects_drop(self) -> None:
        tool = SQLQueryTool()
        result = await tool.execute(query="DROP TABLE users")
        assert not result.success

    @pytest.mark.asyncio
    async def test_sql_query_rejects_delete(self) -> None:
        tool = SQLQueryTool()
        result = await tool.execute(query="DELETE FROM users WHERE id=1")
        assert not result.success

    @pytest.mark.asyncio
    async def test_sql_query_no_database_url(self) -> None:
        tool = SQLQueryTool()
        result = await tool.execute(query="SELECT 1", database_url="")
        assert not result.success
        assert "DATABASE_URL" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sql_write_rejects_ddl(self) -> None:
        tool = SQLWriteTool()
        result = await tool.execute(query="DROP TABLE users")
        assert not result.success
        assert "DDL" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sql_write_rejects_select(self) -> None:
        tool = SQLWriteTool()
        result = await tool.execute(query="SELECT * FROM users")
        assert not result.success


# ---------------------------------------------------------------------------
# Document tools basic tests
# ---------------------------------------------------------------------------

class TestMarkdownToHTML:
    @pytest.mark.asyncio
    async def test_empty_markdown(self) -> None:
        tool = MarkdownToHTMLTool()
        result = await tool.execute(markdown="")
        assert not result.success

    @pytest.mark.asyncio
    async def test_basic_conversion(self) -> None:
        tool = MarkdownToHTMLTool()
        result = await tool.execute(markdown="# Hello World")
        assert result.success
        assert "Hello World" in result.output


# ---------------------------------------------------------------------------
# Email tool placeholder test
# ---------------------------------------------------------------------------

class TestReadEmail:
    @pytest.mark.asyncio
    async def test_read_email_not_configured(self) -> None:
        tool = ReadEmailTool()
        result = await tool.execute(mailbox="INBOX", count=5)
        assert not result.success
        assert "IMAP not configured" in (result.error or "")


# ---------------------------------------------------------------------------
# Page range parser test (document_tools helper)
# ---------------------------------------------------------------------------

class TestPageRangeParser:
    def test_single_page(self) -> None:
        from selva_tools.builtins.document_tools import _parse_page_range

        assert _parse_page_range("3") == [2]  # zero-based

    def test_range(self) -> None:
        from selva_tools.builtins.document_tools import _parse_page_range

        assert _parse_page_range("1-3") == [0, 1, 2]

    def test_mixed(self) -> None:
        from selva_tools.builtins.document_tools import _parse_page_range

        assert _parse_page_range("1,3,5") == [0, 2, 4]
