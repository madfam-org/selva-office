"""Tests for operations tools -- PedimentoLookup, CarrierTracking, InventoryCheck."""

from __future__ import annotations

import pytest

from autoswarm_tools.builtins import get_builtin_tools
from autoswarm_tools.builtins.operations import (
    CarrierTrackingTool,
    InventoryCheckTool,
    PedimentoLookupTool,
)

# -- Registration tests -------------------------------------------------------


class TestToolRegistration:
    """Verify operations tools are registered in the builtin registry."""

    def test_pedimento_lookup_registered(self) -> None:
        tools = get_builtin_tools()
        names = [t.name for t in tools]
        assert "pedimento_lookup" in names

    def test_carrier_tracking_registered(self) -> None:
        tools = get_builtin_tools()
        names = [t.name for t in tools]
        assert "carrier_tracking" in names

    def test_inventory_check_registered(self) -> None:
        tools = get_builtin_tools()
        names = [t.name for t in tools]
        assert "inventory_check" in names


# -- Schema tests -------------------------------------------------------------


class TestPedimentoLookupSchema:
    """Verify PedimentoLookupTool schema and openai spec."""

    def test_schema_has_required_numero(self) -> None:
        tool = PedimentoLookupTool()
        schema = tool.parameters_schema()
        assert "numero" in schema["properties"]
        assert "numero" in schema["required"]

    def test_openai_spec_structure(self) -> None:
        tool = PedimentoLookupTool()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "pedimento_lookup"
        assert "parameters" in spec["function"]


class TestCarrierTrackingSchema:
    """Verify CarrierTrackingTool schema and validation."""

    def test_schema_has_required_fields(self) -> None:
        tool = CarrierTrackingTool()
        schema = tool.parameters_schema()
        assert "carrier" in schema["properties"]
        assert "tracking_number" in schema["properties"]
        assert "carrier" in schema["required"]
        assert "tracking_number" in schema["required"]

    def test_carrier_enum_values(self) -> None:
        tool = CarrierTrackingTool()
        schema = tool.parameters_schema()
        enum_values = schema["properties"]["carrier"]["enum"]
        assert "estafeta" in enum_values
        assert "fedex" in enum_values
        assert "dhl" in enum_values
        assert "paquetexpress" in enum_values

    def test_openai_spec_structure(self) -> None:
        tool = CarrierTrackingTool()
        spec = tool.to_openai_spec()
        assert spec["function"]["name"] == "carrier_tracking"


class TestInventoryCheckSchema:
    """Verify InventoryCheckTool schema."""

    def test_schema_has_required_sku(self) -> None:
        tool = InventoryCheckTool()
        schema = tool.parameters_schema()
        assert "sku" in schema["properties"]
        assert "sku" in schema["required"]

    def test_schema_has_optional_warehouse(self) -> None:
        tool = InventoryCheckTool()
        schema = tool.parameters_schema()
        assert "warehouse" in schema["properties"]
        # warehouse should NOT be in required
        assert "warehouse" not in schema.get("required", [])


# -- Execution tests ----------------------------------------------------------


@pytest.mark.asyncio
async def test_pedimento_lookup_empty_numero() -> None:
    tool = PedimentoLookupTool()
    result = await tool.execute(numero="")
    assert not result.success
    assert "required" in result.error.lower()


@pytest.mark.asyncio
async def test_carrier_tracking_missing_fields() -> None:
    tool = CarrierTrackingTool()
    result = await tool.execute(carrier="", tracking_number="")
    assert not result.success
    assert "required" in result.error.lower()


@pytest.mark.asyncio
async def test_carrier_tracking_invalid_carrier() -> None:
    tool = CarrierTrackingTool()
    result = await tool.execute(carrier="invalid", tracking_number="12345")
    assert not result.success
    assert "unsupported" in result.error.lower()


@pytest.mark.asyncio
async def test_carrier_tracking_not_configured() -> None:
    """Without API keys, carrier tracking returns 'not configured' status."""
    tool = CarrierTrackingTool()
    result = await tool.execute(carrier="estafeta", tracking_number="12345")
    assert result.success
    assert result.data["status"] == "tracking_service_not_configured"
    assert result.data["carrier"] == "estafeta"
    assert result.data["tracking_number"] == "12345"


@pytest.mark.asyncio
async def test_inventory_check_empty_sku() -> None:
    tool = InventoryCheckTool()
    result = await tool.execute(sku="")
    assert not result.success
    assert "required" in result.error.lower()


@pytest.mark.asyncio
async def test_inventory_check_not_configured() -> None:
    """Without adapters, inventory check returns 'not configured'."""
    tool = InventoryCheckTool()
    result = await tool.execute(sku="SKU-001")
    assert result.success
    assert result.data["status"] == "inventory_service_not_configured"
    assert result.data["sku"] == "SKU-001"
