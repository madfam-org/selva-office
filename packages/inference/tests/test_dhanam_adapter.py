"""Tests for the Dhanam billing & wealth adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from madfam_inference.adapters.dhanam import (
    DhanamAdapter,
    DhanamBankStatement,
    DhanamPaymentSummary,
    DhanamTransaction,
)


def _mock_response(data: dict | list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


def _mock_client(method: str = "get", data: dict | list | None = None) -> AsyncMock:
    """Return an AsyncMock httpx client with the specified method mocked."""
    mock_client = AsyncMock()
    getattr(mock_client, method).return_value = _mock_response(data or {})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestDhanamAdapterInit:
    """DhanamAdapter initialization and configuration."""

    def test_default_base_url(self) -> None:
        adapter = DhanamAdapter()
        assert adapter._base_url == "http://localhost:3060"

    def test_custom_base_url(self) -> None:
        adapter = DhanamAdapter(base_url="http://dhanam:9090")
        assert adapter._base_url == "http://dhanam:9090"

    def test_trailing_slash_stripped(self) -> None:
        adapter = DhanamAdapter(base_url="http://dhanam:9090/")
        assert adapter._base_url == "http://dhanam:9090"

    def test_env_var_base_url(self) -> None:
        with patch.dict(
            "os.environ",
            {"DHANAM_API_URL": "http://env-dhanam:3060", "DHANAM_API_TOKEN": "envtok"},
        ):
            adapter = DhanamAdapter()
        assert adapter._base_url == "http://env-dhanam:3060"
        assert adapter._token == "envtok"

    def test_auth_header_present_when_token_set(self) -> None:
        adapter = DhanamAdapter(token="my-token")
        headers = adapter._headers()
        assert headers["Authorization"] == "Bearer my-token"

    def test_no_auth_header_when_token_empty(self) -> None:
        adapter = DhanamAdapter(token="")
        headers = adapter._headers()
        assert "Authorization" not in headers


class TestListTransactions:
    """DhanamAdapter.list_transactions() method."""

    @pytest.mark.asyncio
    async def test_returns_transactions(self) -> None:
        client = _mock_client("get", [
            {
                "id": "txn-1",
                "amount": "1000.00",
                "currency": "MXN",
                "description": "Pago servicio",
                "category": "income",
                "date": "2026-04-05",
                "payment_method": "spei",
                "cfdi_uuid": "cfdi-abc",
                "counterparty_rfc": "XAXX010101000",
                "status": "completed",
            },
        ])

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.list_transactions("org-1", "2026-04-01", "2026-05-01")

        assert len(result) == 1
        assert isinstance(result[0], DhanamTransaction)
        assert result[0].id == "txn-1"
        assert result[0].amount == "1000.00"
        assert result[0].payment_method == "spei"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060")
            result = await adapter.list_transactions("org-1", "2026-04-01", "2026-05-01")

        assert result == []

    @pytest.mark.asyncio
    async def test_passes_query_params(self) -> None:
        client = _mock_client("get", [])

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            await adapter.list_transactions("org-1", "2026-04-01", "2026-05-01")

        call_kwargs = client.get.call_args
        assert call_kwargs[1]["params"]["since"] == "2026-04-01"
        assert call_kwargs[1]["params"]["until"] == "2026-05-01"


class TestGetBankStatements:
    """DhanamAdapter.get_bank_statements() method."""

    @pytest.mark.asyncio
    async def test_returns_statements(self) -> None:
        client = _mock_client("get", [
            {
                "account_id": "acct-1",
                "account_name": "BBVA Empresarial",
                "institution": "BBVA",
                "balance": "50000.00",
                "currency": "MXN",
                "transactions": [],
            },
        ])

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_bank_statements("org-1")

        assert len(result) == 1
        assert isinstance(result[0], DhanamBankStatement)
        assert result[0].account_id == "acct-1"
        assert result[0].institution == "BBVA"

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter()
            result = await adapter.get_bank_statements("org-1")

        assert result == []


class TestGetPaymentSummary:
    """DhanamAdapter.get_payment_summary() method."""

    @pytest.mark.asyncio
    async def test_returns_summary(self) -> None:
        client = _mock_client("get", {
            "period": "2026-04",
            "total_income": "150000.00",
            "total_expenses": "80000.00",
            "by_method": {
                "stripe_mx": "60000.00",
                "oxxo": "20000.00",
                "spei": "50000.00",
                "conekta": "10000.00",
                "transfer": "10000.00",
            },
        })

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_payment_summary("org-1", "2026-04")

        assert isinstance(result, DhanamPaymentSummary)
        assert result.total_income == "150000.00"
        assert result.by_method["stripe_mx"] == "60000.00"

    @pytest.mark.asyncio
    async def test_returns_empty_summary_on_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter()
            result = await adapter.get_payment_summary("org-1", "2026-04")

        assert isinstance(result, DhanamPaymentSummary)
        assert result.total_income == "0.00"
        assert result.period == "2026-04"


class TestGetPosTransactions:
    """DhanamAdapter.get_pos_transactions() method."""

    @pytest.mark.asyncio
    async def test_returns_pos_transactions(self) -> None:
        client = _mock_client("get", [
            {
                "id": "pos-1",
                "amount": "500.00",
                "currency": "MXN",
                "description": "Terminal sale",
                "payment_method": "stripe_mx",
                "date": "2026-04-10",
                "status": "completed",
            },
        ])

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_pos_transactions("org-1", "2026-04-01", "2026-05-01")

        assert len(result) == 1
        assert result[0].payment_method == "stripe_mx"


class TestGetTransaction:
    """DhanamAdapter.get_transaction() method (used by billing graph)."""

    @pytest.mark.asyncio
    async def test_returns_transaction_dict(self) -> None:
        client = _mock_client("get", {
            "id": "txn-99",
            "emisor_rfc": "AAA",
            "receptor_rfc": "BBB",
            "conceptos": [{"desc": "item"}],
        })

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_transaction("txn-99")

        assert result["id"] == "txn-99"
        assert result["emisor_rfc"] == "AAA"

    @pytest.mark.asyncio
    async def test_returns_empty_dict_on_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter()
            result = await adapter.get_transaction("txn-99")

        assert result == {}


class TestBillingModuleReexport:
    """The billing.py re-export module works for existing billing graph imports."""

    def test_import_from_billing(self) -> None:
        from madfam_inference.adapters.billing import DhanamAdapter as BillingAdapter

        assert BillingAdapter is DhanamAdapter
