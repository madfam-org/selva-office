"""Tests for LFPDPPP privacy tools."""

from __future__ import annotations

import pytest

from selva_tools.builtins.privacy import (
    DataDeletionTool,
    PIIClassificationTool,
    PrivacyNoticeGeneratorTool,
)


class TestPIIClassificationTool:
    """PII classification detects Mexican PII patterns."""

    @pytest.mark.asyncio
    async def test_pii_classify_detects_rfc(self) -> None:
        tool = PIIClassificationTool()
        result = await tool.execute(text="El RFC del cliente es XAXX010101000.")
        assert result.success
        assert result.data["has_pii"] is True
        types = [f["type"] for f in result.data["findings"]]
        assert "RFC" in types

    @pytest.mark.asyncio
    async def test_pii_classify_detects_curp(self) -> None:
        tool = PIIClassificationTool()
        result = await tool.execute(text="CURP: GARC850101HDFRRL09")
        assert result.success
        assert result.data["has_pii"] is True
        types = [f["type"] for f in result.data["findings"]]
        assert "CURP" in types

    @pytest.mark.asyncio
    async def test_pii_classify_detects_email(self) -> None:
        tool = PIIClassificationTool()
        result = await tool.execute(text="Contacto: persona@example.com")
        assert result.success
        assert result.data["has_pii"] is True
        types = [f["type"] for f in result.data["findings"]]
        assert "email" in types

    @pytest.mark.asyncio
    async def test_pii_classify_no_pii(self) -> None:
        tool = PIIClassificationTool()
        result = await tool.execute(text="This is a plain text without any PII.")
        assert result.success
        assert result.data["has_pii"] is False
        assert result.data["findings"] == []

    @pytest.mark.asyncio
    async def test_pii_classify_empty_text(self) -> None:
        tool = PIIClassificationTool()
        result = await tool.execute(text="")
        assert not result.success
        assert "required" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_pii_classify_redacts_matches(self) -> None:
        tool = PIIClassificationTool()
        result = await tool.execute(text="RFC: XAXX010101000 y GARC850101AAA")
        rfc_finding = next(
            f for f in result.data["findings"] if f["type"] == "RFC"
        )
        assert rfc_finding["count"] == 2
        # Redacted values should only show first 4 chars
        for r in rfc_finding["redacted"]:
            assert r.endswith("***")
            assert len(r) == 7  # 4 chars + "***"

    def test_pii_tool_schema(self) -> None:
        tool = PIIClassificationTool()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "text" in schema["properties"]
        assert "text" in schema["required"]

    def test_pii_tool_openai_spec(self) -> None:
        tool = PIIClassificationTool()
        spec = tool.to_openai_spec()
        assert spec["function"]["name"] == "pii_classify"


class TestPrivacyNoticeGeneratorTool:
    """Privacy notice generation for LFPDPPP compliance."""

    @pytest.mark.asyncio
    async def test_privacy_notice_generates_valid(self) -> None:
        tool = PrivacyNoticeGeneratorTool()
        result = await tool.execute(
            razon_social="Empresa SA de CV",
            rfc="XAXX010101000",
            domicilio="Calle Reforma 222, CDMX",
        )
        assert result.success
        assert "AVISO DE PRIVACIDAD" in result.output
        assert "LFPDPPP" in result.output
        assert "Empresa SA de CV" in result.output
        assert "XAXX010101000" in result.output
        assert "DERECHOS ARCO" in result.output
        assert result.data["word_count"] > 0

    @pytest.mark.asyncio
    async def test_privacy_notice_requires_fields(self) -> None:
        tool = PrivacyNoticeGeneratorTool()
        result = await tool.execute(razon_social="", rfc="")
        assert not result.success
        assert "required" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_privacy_notice_custom_purposes(self) -> None:
        tool = PrivacyNoticeGeneratorTool()
        result = await tool.execute(
            razon_social="Test Corp",
            rfc="TEST010101AAA",
            data_purposes=["Nomina", "Control de acceso"],
        )
        assert result.success
        assert "Nomina" in result.output
        assert "Control de acceso" in result.output

    @pytest.mark.asyncio
    async def test_privacy_notice_custom_email(self) -> None:
        tool = PrivacyNoticeGeneratorTool()
        result = await tool.execute(
            razon_social="Test Corp",
            rfc="TEST010101AAA",
            contact_email="datos@testcorp.mx",
        )
        assert result.success
        assert "datos@testcorp.mx" in result.output

    def test_privacy_notice_schema(self) -> None:
        tool = PrivacyNoticeGeneratorTool()
        schema = tool.parameters_schema()
        assert "razon_social" in schema["required"]
        assert "rfc" in schema["required"]


class TestDataDeletionTool:
    """Data deletion search for LFPDPPP right-to-deletion."""

    @pytest.mark.asyncio
    async def test_data_deletion_requires_term(self) -> None:
        tool = DataDeletionTool()
        result = await tool.execute(search_term="")
        assert not result.success
        assert "required" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_data_deletion_returns_hitl_status(self) -> None:
        tool = DataDeletionTool()
        result = await tool.execute(search_term="XAXX010101000")
        assert result.success
        assert result.data["status"] == "requires_hitl_approval"
        assert result.data["search_term"] == "XAXX010101000"

    @pytest.mark.asyncio
    async def test_data_deletion_custom_scope(self) -> None:
        tool = DataDeletionTool()
        result = await tool.execute(
            search_term="persona@example.com",
            scope=["chat", "events"],
        )
        assert result.success
        assert result.data["scopes_searched"] == ["chat", "events"]

    @pytest.mark.asyncio
    async def test_data_deletion_default_scope(self) -> None:
        tool = DataDeletionTool()
        result = await tool.execute(search_term="any-term")
        assert result.success
        assert set(result.data["scopes_searched"]) == {
            "artifacts", "events", "chat", "memory"
        }

    def test_data_deletion_schema(self) -> None:
        tool = DataDeletionTool()
        schema = tool.parameters_schema()
        assert "search_term" in schema["required"]


class TestPrivacyToolsRegistered:
    """Privacy tools are registered in get_builtin_tools()."""

    def test_all_registered_in_builtins(self) -> None:
        from selva_tools.builtins import get_builtin_tools

        tools = get_builtin_tools()
        names = {t.name for t in tools}
        assert "pii_classify" in names
        assert "privacy_notice_generate" in names
        assert "data_deletion_search" in names
