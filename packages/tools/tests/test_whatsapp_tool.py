"""Tests for the WhatsAppTemplateTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from selva_tools.builtins import get_builtin_tools
from selva_tools.builtins.whatsapp import TEMPLATE_CATALOG, WhatsAppTemplateTool


class TestWhatsAppToolMetadata:
    def test_schema_is_valid(self) -> None:
        tool = WhatsAppTemplateTool()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "phone" in schema["properties"]
        assert "template_name" in schema["properties"]
        assert "parameters" in schema["properties"]
        assert "language" in schema["properties"]
        assert "phone" in schema["required"]
        assert "template_name" in schema["required"]
        assert "parameters" in schema["required"]
        # template_name enum matches catalog keys
        assert set(schema["properties"]["template_name"]["enum"]) == set(TEMPLATE_CATALOG.keys())

    def test_template_catalog_has_4_entries(self) -> None:
        assert len(TEMPLATE_CATALOG) == 4
        expected = {
            "factura_enviada",
            "recordatorio_pago",
            "confirmacion_pedido",
            "cotizacion_lista",
        }
        assert set(TEMPLATE_CATALOG.keys()) == expected

    def test_openai_spec_format(self) -> None:
        tool = WhatsAppTemplateTool()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "whatsapp_send_template"
        assert "parameters" in spec["function"]
        assert "description" in spec["function"]

    def test_each_template_has_required_fields(self) -> None:
        for name, tmpl in TEMPLATE_CATALOG.items():
            assert "name" in tmpl, f"{name} missing 'name'"
            assert "language" in tmpl, f"{name} missing 'language'"
            assert "description" in tmpl, f"{name} missing 'description'"
            assert "parameters" in tmpl, f"{name} missing 'parameters'"
            assert isinstance(tmpl["parameters"], list)


class TestWhatsAppToolRegistration:
    def test_registered_in_builtin_tools(self) -> None:
        tools = get_builtin_tools()
        tool_names = [t.name for t in tools]
        assert "whatsapp_send_template" in tool_names

    def test_builtin_instance_type(self) -> None:
        tools = get_builtin_tools()
        wa_tools = [t for t in tools if t.name == "whatsapp_send_template"]
        assert len(wa_tools) == 1
        assert isinstance(wa_tools[0], WhatsAppTemplateTool)


class TestWhatsAppToolExecution:
    @pytest.mark.asyncio
    async def test_rejects_missing_phone(self) -> None:
        tool = WhatsAppTemplateTool()
        result = await tool.execute(
            phone="",
            template_name="factura_enviada",
            parameters=["Name", "UUID", "1000", "https://example.com"],
        )
        assert not result.success
        assert "Phone number is required" in (result.error or "")

    @pytest.mark.asyncio
    async def test_rejects_unknown_template(self) -> None:
        tool = WhatsAppTemplateTool()
        result = await tool.execute(
            phone="+5215512345678",
            template_name="nonexistent_template",
            parameters=["a"],
        )
        assert not result.success
        assert "Unknown template" in (result.error or "")
        assert "nonexistent_template" in (result.error or "")

    @pytest.mark.asyncio
    async def test_rejects_missing_credentials(self) -> None:
        tool = WhatsAppTemplateTool()
        with patch.dict(
            "os.environ",
            {"WHATSAPP_ACCESS_TOKEN": "", "WHATSAPP_PHONE_NUMBER_ID": ""},
            clear=False,
        ):
            result = await tool.execute(
                phone="+5215512345678",
                template_name="factura_enviada",
                parameters=["Name", "UUID", "1000", "https://example.com"],
            )
        assert not result.success
        assert "WHATSAPP_ACCESS_TOKEN" in (result.error or "")

    @pytest.mark.asyncio
    async def test_rejects_missing_phone_number_id(self) -> None:
        tool = WhatsAppTemplateTool()
        with patch.dict(
            "os.environ",
            {"WHATSAPP_ACCESS_TOKEN": "valid-token", "WHATSAPP_PHONE_NUMBER_ID": ""},
            clear=False,
        ):
            result = await tool.execute(
                phone="+5215512345678",
                template_name="factura_enviada",
                parameters=["Name", "UUID", "1000", "https://example.com"],
            )
        assert not result.success
        assert "WHATSAPP_PHONE_NUMBER_ID" in (result.error or "")

    @pytest.mark.asyncio
    async def test_sends_template_successfully(self) -> None:
        tool = WhatsAppTemplateTool()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "messages": [{"id": "wamid.HBgLMTU1MTIzNDU2Nzg"}],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict(
                "os.environ",
                {
                    "WHATSAPP_ACCESS_TOKEN": "test-token-123",
                    "WHATSAPP_PHONE_NUMBER_ID": "1234567890",
                },
            ),
        ):
            result = await tool.execute(
                phone="+5215512345678",
                template_name="factura_enviada",
                parameters=["Juan Perez", "UUID-ABC", "1500.00", "https://dl.co/inv"],
            )

        assert result.success
        assert "factura_enviada" in result.output
        assert "+5215512345678" in result.output
        assert result.data["message_id"] == "wamid.HBgLMTU1MTIzNDU2Nzg"
        assert result.data["template"] == "factura_enviada"
        assert result.data["phone"] == "+5215512345678"

        # Verify the POST was called with the correct URL and payload
        call_kwargs = mock_client.post.call_args
        url = call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs.get("url")
        assert "graph.facebook.com" in url
        assert "1234567890" in url

        json_payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert json_payload["messaging_product"] == "whatsapp"
        assert json_payload["to"] == "+5215512345678"
        assert json_payload["type"] == "template"
        assert json_payload["template"]["name"] == "factura_enviada"
        assert json_payload["template"]["language"]["code"] == "es_MX"

        body_params = json_payload["template"]["components"][0]["parameters"]
        assert len(body_params) == 4
        assert body_params[0]["text"] == "Juan Perez"
        assert body_params[1]["text"] == "UUID-ABC"

    @pytest.mark.asyncio
    async def test_sends_with_custom_language(self) -> None:
        tool = WhatsAppTemplateTool()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"messages": [{"id": "msg-123"}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict(
                "os.environ",
                {
                    "WHATSAPP_ACCESS_TOKEN": "tk",
                    "WHATSAPP_PHONE_NUMBER_ID": "pid",
                },
            ),
        ):
            result = await tool.execute(
                phone="+5215500000000",
                template_name="confirmacion_pedido",
                parameters=["Maria", "ORD-99", "2026-04-20"],
                language="es",
            )

        assert result.success
        json_payload = mock_client.post.call_args.kwargs.get("json")
        assert json_payload["template"]["language"]["code"] == "es"

    @pytest.mark.asyncio
    async def test_handles_api_error(self) -> None:
        tool = WhatsAppTemplateTool()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch.dict(
                "os.environ",
                {
                    "WHATSAPP_ACCESS_TOKEN": "tk",
                    "WHATSAPP_PHONE_NUMBER_ID": "pid",
                },
            ),
        ):
            result = await tool.execute(
                phone="+5215512345678",
                template_name="recordatorio_pago",
                parameters=["Ana", "INV-001", "500.00", "2026-04-30"],
            )

        assert not result.success
        assert "Connection refused" in (result.error or "")
