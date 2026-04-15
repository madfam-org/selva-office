"""Tests for the Banxico SIE adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from madfam_inference.adapters.banxico import (
    BanxicoAdapter,
    EconomicIndicator,
    ExchangeRate,
)


def _make_banxico_response(series_id: str, fecha: str, dato: str) -> dict:
    """Build a Banxico SIE-format response."""
    return {
        "bmx": {
            "series": [
                {
                    "idSerie": series_id,
                    "datos": [{"fecha": fecha, "dato": dato}],
                }
            ]
        }
    }


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


def _mock_client(data: dict) -> AsyncMock:
    """Return an AsyncMock httpx client with GET mocked."""
    mock_client = AsyncMock()
    mock_client.get.return_value = _mock_response(data)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestBanxicoAdapterInit:
    """BanxicoAdapter constructor and configuration."""

    def test_default_token_empty(self) -> None:
        adapter = BanxicoAdapter()
        assert adapter._token == ""

    def test_custom_token(self) -> None:
        adapter = BanxicoAdapter(token="my-banxico-token")
        assert adapter._token == "my-banxico-token"

    def test_env_token(self) -> None:
        with patch.dict("os.environ", {"BANXICO_API_TOKEN": "env-tok"}):
            adapter = BanxicoAdapter()
        assert adapter._token == "env-tok"

    def test_bmx_token_header_present(self) -> None:
        adapter = BanxicoAdapter(token="tok")
        headers = adapter._headers()
        assert headers["Bmx-Token"] == "tok"

    def test_no_bmx_token_header_when_empty(self) -> None:
        adapter = BanxicoAdapter(token="")
        headers = adapter._headers()
        assert "Bmx-Token" not in headers


class TestExtractLatest:
    """_extract_latest() parses Banxico SIE response format."""

    def test_valid_response(self) -> None:
        data = _make_banxico_response("SF43718", "14/04/2026", "17.0500")
        date, value = BanxicoAdapter._extract_latest(data)
        assert date == "14/04/2026"
        assert value == "17.0500"

    def test_empty_series(self) -> None:
        data = {"bmx": {"series": []}}
        date, value = BanxicoAdapter._extract_latest(data)
        assert date == ""
        assert value == ""

    def test_empty_datos(self) -> None:
        data = {"bmx": {"series": [{"datos": []}]}}
        date, value = BanxicoAdapter._extract_latest(data)
        assert date == ""
        assert value == ""

    def test_malformed_response(self) -> None:
        date, value = BanxicoAdapter._extract_latest({})
        assert date == ""
        assert value == ""


class TestGetExchangeRate:
    """get_exchange_rate() fetches USD/MXN FIX rate."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        data = _make_banxico_response("SF43718", "14/04/2026", "17.0500")
        client = _mock_client(data)

        with patch(
            "madfam_inference.adapters.banxico.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = BanxicoAdapter(token="t")
            result = await adapter.get_exchange_rate("USD")

        assert isinstance(result, ExchangeRate)
        assert result.rate == "17.0500"
        assert result.currency_pair == "USD/MXN"
        assert result.date == "14/04/2026"

    @pytest.mark.asyncio
    async def test_error_returns_empty(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.banxico.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = BanxicoAdapter()
            result = await adapter.get_exchange_rate()

        assert isinstance(result, ExchangeRate)
        assert result.rate == ""


class TestGetTIIE:
    """get_tiie() fetches TIIE interest rate."""

    @pytest.mark.asyncio
    async def test_tiie_28(self) -> None:
        data = _make_banxico_response("SF43783", "14/04/2026", "11.2500")
        client = _mock_client(data)

        with patch(
            "madfam_inference.adapters.banxico.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = BanxicoAdapter(token="t")
            result = await adapter.get_tiie("28")

        assert isinstance(result, EconomicIndicator)
        assert result.series_id == "SF43783"
        assert result.value == "11.2500"

    @pytest.mark.asyncio
    async def test_tiie_91(self) -> None:
        data = _make_banxico_response("SF43784", "14/04/2026", "11.5000")
        client = _mock_client(data)

        with patch(
            "madfam_inference.adapters.banxico.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = BanxicoAdapter(token="t")
            result = await adapter.get_tiie("91")

        assert isinstance(result, EconomicIndicator)
        assert result.series_id == "SF43784"
        assert result.value == "11.5000"


class TestGetInflation:
    """get_inflation() fetches annual CPI/INPC rate."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        data = _make_banxico_response("SP74665", "14/04/2026", "4.2100")
        client = _mock_client(data)

        with patch(
            "madfam_inference.adapters.banxico.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = BanxicoAdapter(token="t")
            result = await adapter.get_inflation()

        assert isinstance(result, EconomicIndicator)
        assert result.series_id == "SP74665"
        assert result.value == "4.2100"
        assert "INPC" in result.name


class TestGetUMA:
    """get_uma() fetches daily UMA value."""

    @pytest.mark.asyncio
    async def test_success(self) -> None:
        data = _make_banxico_response("SP74668", "14/04/2026", "113.14")
        client = _mock_client(data)

        with patch(
            "madfam_inference.adapters.banxico.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = BanxicoAdapter(token="t")
            result = await adapter.get_uma()

        assert isinstance(result, EconomicIndicator)
        assert result.series_id == "SP74668"
        assert result.value == "113.14"
        assert "UMA" in result.name
