"""Tests for the Dhanam billing & wealth adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from madfam_inference.adapters.dhanam import (
    DhanamAdapter,
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


def _row(identifier="synthetic-1"):
    return {
        "id": identifier,
        "amount": "100.00",
        "currency": "MXN",
        "accountId": "synthetic-account",
        "date": "2026-04-05T00:00:00Z",
        "category": {"id": "synthetic-category", "name": "Synthetic"},
    }


def _page(rows, total, page=1):
    return {"data": rows, "total": total, "page": page, "limit": 100}


class TestListTransactions:
    @pytest.mark.asyncio
    async def test_reads_all_pages_with_proof_and_actual_date_parameters(self):
        client = _mock_client()
        client.get.side_effect = [
            _mock_response(_page([_row(str(i)) for i in range(100)], 101)),
            _mock_response(_page([_row("last")], 101, 2)),
        ]
        with patch("madfam_inference.adapters.dhanam.httpx.AsyncClient", return_value=client):
            result = await DhanamAdapter(
                base_url="https://example.invalid", token="synthetic"
            ).list_transactions("synthetic-space", "2026-04-01", "2026-05-01")
        assert len(result.items) == result.proof.total == 101
        assert result.proof.pages_read == 2
        assert result.proof.scope_id == "synthetic-space"
        assert result.items[-1]["id"] == "last"
        for index, call in enumerate(client.get.call_args_list, 1):
            params = call.kwargs["params"]
            assert params["startDate"] == "2026-04-01T00:00:00+00:00"
            assert params["endDate"] == "2026-04-30T23:59:59.999000+00:00"
            assert params["page"] == index
            assert "since" not in params and "until" not in params

    @pytest.mark.asyncio
    async def test_verified_empty_has_an_explicit_source_proof(self):
        client = _mock_client(data=_page([], 0))
        with patch("madfam_inference.adapters.dhanam.httpx.AsyncClient", return_value=client):
            result = await DhanamAdapter(
                base_url="https://example.invalid", token="synthetic"
            ).list_transactions("synthetic-space", "2026-04-01", "2026-05-01")
        assert result.items == []
        assert result.proof.status == "complete"
        assert result.proof.total == 0
        assert result.proof.pages_read == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "responses",
        [
            [[]],
            [[_row()]],
            [{}],
            [{"data": [], "total": 0}],
            [_page([], 1)],
            [_page([_row()], 101)],
            [_page([_row()], 0)],
            [_page([], True)],
            [_page([_row(str(i)) for i in range(100)], 101), _page([], 101, 2)],
            [_page([_row(str(i)) for i in range(100)], 101), _page([_row("0")], 101, 2)],
            [_page([_row(str(i)) for i in range(100)], 101), _page([_row("last")], 102, 2)],
            [_page([_row(str(i)) for i in range(100)], 101), _page([_row("last")], 101, 1)],
            [_page([{**_row(), "date": "2026-05-01T00:00:00Z"}], 1)],
            [_page([{**_row(), "currency": ""}], 1)],
            [_page([{**_row(), "amount": "NaN"}], 1)],
            [_page([{**_row(), "accountId": ""}], 1)],
            [_page([{**_row(), "spaceId": "other-space"}], 1)],
        ],
    )
    async def test_no_partial_or_incompatible_read_is_returned(self, responses):
        from madfam_inference.adapters.financial_reads import FinancialReadUnavailableError

        client = _mock_client()
        client.get.side_effect = [_mock_response(body) for body in responses]
        with patch("madfam_inference.adapters.dhanam.httpx.AsyncClient", return_value=client):
            with pytest.raises(
                FinancialReadUnavailableError, match="dhanam_transactions_unavailable"
            ):
                await DhanamAdapter(
                    base_url="https://example.invalid", token="synthetic"
                ).list_transactions("synthetic-space", "2026-04-01", "2026-05-01")

    @pytest.mark.asyncio
    async def test_failure_after_first_page_does_not_return_partial_data(self, caplog):
        import httpx

        from madfam_inference.adapters.financial_reads import FinancialReadUnavailableError

        client = _mock_client()
        client.get.side_effect = [
            _mock_response(_page([_row(str(i)) for i in range(100)], 101)),
            httpx.ReadTimeout("SENSITIVE_SENTINEL"),
        ]
        with patch("madfam_inference.adapters.dhanam.httpx.AsyncClient", return_value=client):
            with pytest.raises(FinancialReadUnavailableError) as error:
                await DhanamAdapter(
                    base_url="https://example.invalid", token="synthetic"
                ).list_transactions("synthetic-space", "2026-04-01", "2026-05-01")
        assert "SENSITIVE_SENTINEL" not in str(error.value) + caplog.text

    @pytest.mark.asyncio
    async def test_unconfigured_source_makes_no_request(self, monkeypatch):
        from madfam_inference.adapters.financial_reads import FinancialReadUnavailableError

        monkeypatch.delenv("DHANAM_API_URL", raising=False)
        monkeypatch.delenv("DHANAM_API_TOKEN", raising=False)
        with patch("madfam_inference.adapters.dhanam.httpx.AsyncClient") as client:
            with pytest.raises(FinancialReadUnavailableError):
                await DhanamAdapter().list_transactions(
                    "synthetic-space", "2026-04-01", "2026-05-01"
                )
        client.assert_not_called()


class TestUnavailableAccountingContracts:
    @pytest.mark.asyncio
    async def test_unverified_routes_never_fabricate_zero_data(self):
        from madfam_inference.adapters.financial_reads import FinancialReadUnavailableError
        from madfam_inference.adapters.karafiel import KarafielAdapter

        adapter = DhanamAdapter(base_url="https://example.invalid", token="synthetic")
        with patch("httpx.AsyncClient") as client:
            for operation, args in (
                (adapter.get_bank_statements, ("synthetic-space",)),
                (adapter.get_payment_summary, ("synthetic-space", "2026-04")),
                (adapter.get_pos_transactions, ("synthetic-space", "2026-04-01", "2026-05-01")),
                (KarafielAdapter().list_cfdis, ("XEXX010101000", "2026-04-01", "2026-05-01")),
            ):
                with pytest.raises(FinancialReadUnavailableError, match="contract_unavailable"):
                    await operation(*args)
        client.assert_not_called()


class TestGetTransaction:
    """DhanamAdapter.get_transaction() method (used by billing graph)."""

    @pytest.mark.asyncio
    async def test_returns_transaction_dict(self) -> None:
        client = _mock_client(
            "get",
            {
                "id": "txn-99",
                "emisor_rfc": "AAA",
                "receptor_rfc": "BBB",
                "conceptos": [{"desc": "item"}],
            },
        )

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


class TestGetExchangeRate:
    """DhanamAdapter.get_exchange_rate() -- economic data via Dhanam market API."""

    @pytest.mark.asyncio
    async def test_get_exchange_rate_success(self) -> None:
        from madfam_inference.adapters.dhanam import ExchangeRate

        client = _mock_client(
            "get",
            {
                "date": "14/04/2026",
                "rate": "17.0500",
                "currency_pair": "USD/MXN",
            },
        )

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_exchange_rate("USD")

        assert isinstance(result, ExchangeRate)
        assert result.rate == "17.0500"
        assert result.currency_pair == "USD/MXN"
        assert result.date == "14/04/2026"

    @pytest.mark.asyncio
    async def test_get_exchange_rate_error_returns_default(self) -> None:
        import httpx as httpx_mod

        from madfam_inference.adapters.dhanam import ExchangeRate

        client = AsyncMock()
        client.get.side_effect = httpx_mod.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter()
            result = await adapter.get_exchange_rate("USD")

        assert isinstance(result, ExchangeRate)
        assert result.rate == ""
        assert result.currency_pair == "USD/MXN"


class TestGetTIIE:
    """DhanamAdapter.get_tiie() -- TIIE rate via Dhanam market API."""

    @pytest.mark.asyncio
    async def test_get_tiie_success(self) -> None:
        from madfam_inference.adapters.dhanam import EconomicIndicator

        client = _mock_client(
            "get",
            {
                "series_id": "SF43783",
                "name": "TIIE 28 dias",
                "date": "14/04/2026",
                "value": "11.2500",
            },
        )

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_tiie("28")

        assert isinstance(result, EconomicIndicator)
        assert result.series_id == "SF43783"
        assert result.value == "11.2500"

    @pytest.mark.asyncio
    async def test_get_tiie_error_returns_default(self) -> None:
        import httpx as httpx_mod

        from madfam_inference.adapters.dhanam import EconomicIndicator

        client = AsyncMock()
        client.get.side_effect = httpx_mod.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter()
            result = await adapter.get_tiie("28")

        assert isinstance(result, EconomicIndicator)
        assert result.value == ""
        assert "TIIE" in result.name


class TestGetInflation:
    """DhanamAdapter.get_inflation() -- CPI/INPC via Dhanam market API."""

    @pytest.mark.asyncio
    async def test_get_inflation_success(self) -> None:
        from madfam_inference.adapters.dhanam import EconomicIndicator

        client = _mock_client(
            "get",
            {
                "series_id": "SP74665",
                "name": "INPC Variacion Anual",
                "date": "14/04/2026",
                "value": "4.2100",
            },
        )

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_inflation()

        assert isinstance(result, EconomicIndicator)
        assert result.series_id == "SP74665"
        assert result.value == "4.2100"
        assert "INPC" in result.name

    @pytest.mark.asyncio
    async def test_get_inflation_error_returns_default(self) -> None:
        import httpx as httpx_mod

        from madfam_inference.adapters.dhanam import EconomicIndicator

        client = AsyncMock()
        client.get.side_effect = httpx_mod.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter()
            result = await adapter.get_inflation()

        assert isinstance(result, EconomicIndicator)
        assert result.value == ""
        assert "INPC" in result.name


class TestGetUMA:
    """DhanamAdapter.get_uma() -- UMA value via Dhanam market API."""

    @pytest.mark.asyncio
    async def test_get_uma_success(self) -> None:
        from madfam_inference.adapters.dhanam import EconomicIndicator

        client = _mock_client(
            "get",
            {
                "series_id": "SP74668",
                "name": "UMA Valor Diario",
                "date": "14/04/2026",
                "value": "113.14",
            },
        )

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter(base_url="http://dhanam:3060", token="t")
            result = await adapter.get_uma()

        assert isinstance(result, EconomicIndicator)
        assert result.series_id == "SP74668"
        assert result.value == "113.14"
        assert "UMA" in result.name

    @pytest.mark.asyncio
    async def test_get_uma_error_returns_default(self) -> None:
        import httpx as httpx_mod

        from madfam_inference.adapters.dhanam import EconomicIndicator

        client = AsyncMock()
        client.get.side_effect = httpx_mod.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.dhanam.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = DhanamAdapter()
            result = await adapter.get_uma()

        assert isinstance(result, EconomicIndicator)
        assert result.value == ""
        assert "UMA" in result.name


class TestBillingModuleReexport:
    """The billing.py re-export module works for existing billing graph imports."""

    def test_import_from_billing(self) -> None:
        from madfam_inference.adapters.billing import DhanamAdapter as BillingAdapter

        assert BillingAdapter is DhanamAdapter
