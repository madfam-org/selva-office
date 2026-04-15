"""Banxico SIE adapter -- Mexican central bank economic data."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# --- Response Models ---


class ExchangeRate(BaseModel):
    date: str = ""
    rate: str = ""
    currency_pair: str = "USD/MXN"


class EconomicIndicator(BaseModel):
    series_id: str = ""
    name: str = ""
    date: str = ""
    value: str = ""


# --- Series ID Reference ---
# SF43718 = USD/MXN fix rate (tipo de cambio FIX)
# SF43783 = TIIE 28 days
# SF43784 = TIIE 91 days
# SP74665 = CPI (INPC) annual variation
# SP74668 = UMA daily value

_SERIES_MAP: dict[str, str] = {
    "usd_mxn": "SF43718",
    "tiie_28": "SF43783",
    "tiie_91": "SF43784",
    "inflation": "SP74665",
    "uma": "SP74668",
}

_SERIES_NAMES: dict[str, str] = {
    "SF43718": "Tipo de Cambio FIX USD/MXN",
    "SF43783": "TIIE 28 dias",
    "SF43784": "TIIE 91 dias",
    "SP74665": "INPC Variacion Anual",
    "SP74668": "UMA Valor Diario",
}


# --- Adapter ---


class BanxicoAdapter:
    """Async client wrapping the Banxico SIE REST API.

    Banxico requires a free API token (Bmx-Token header) for higher rate
    limits but basic access works without one for some endpoints.
    All methods return typed Pydantic models and degrade gracefully on error.
    """

    BASE_URL = "https://www.banxico.org.mx/SieAPIRest/service/v1"

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.environ.get("BANXICO_API_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Accept": "application/json"}
        if self._token:
            h["Bmx-Token"] = self._token
        return h

    async def _fetch_series(self, series_id: str) -> dict[str, Any]:
        """Fetch the latest value for a Banxico SIE series.

        Returns the parsed JSON response or an empty dict on error.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self.BASE_URL}/series/{series_id}/datos/oportuno",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Banxico fetch for series %s failed: %s", series_id, exc)
            return {}

    @staticmethod
    def _extract_latest(data: dict[str, Any]) -> tuple[str, str]:
        """Extract the latest (date, value) from Banxico SIE response format.

        Banxico wraps data as::

            {"bmx": {"series": [{"datos": [{"fecha": "...", "dato": "..."}]}]}}
        """
        try:
            series_list = data.get("bmx", {}).get("series", [])
            if not series_list:
                return ("", "")
            datos = series_list[0].get("datos", [])
            if not datos:
                return ("", "")
            latest = datos[-1]
            return (latest.get("fecha", ""), latest.get("dato", ""))
        except (KeyError, IndexError, TypeError):
            return ("", "")

    # -- Public methods ---------------------------------------------------------

    async def get_exchange_rate(self, currency: str = "USD") -> ExchangeRate:
        """Get current USD/MXN exchange rate from Banxico.

        Args:
            currency: Currency code (currently only USD supported by FIX rate).

        Returns:
            ExchangeRate with date, rate, and currency_pair.
        """
        series_id = _SERIES_MAP["usd_mxn"]
        data = await self._fetch_series(series_id)
        date, value = self._extract_latest(data)
        return ExchangeRate(
            date=date,
            rate=value,
            currency_pair=f"{currency}/MXN",
        )

    async def get_tiie(self, term: str = "28") -> EconomicIndicator:
        """Get current TIIE interbank interest rate.

        Args:
            term: Term in days -- "28" or "91".

        Returns:
            EconomicIndicator with TIIE value.
        """
        key = f"tiie_{term}"
        series_id = _SERIES_MAP.get(key, _SERIES_MAP["tiie_28"])
        data = await self._fetch_series(series_id)
        date, value = self._extract_latest(data)
        return EconomicIndicator(
            series_id=series_id,
            name=_SERIES_NAMES.get(series_id, f"TIIE {term} dias"),
            date=date,
            value=value,
        )

    async def get_inflation(self) -> EconomicIndicator:
        """Get current Mexican CPI (INPC) annual inflation rate.

        Returns:
            EconomicIndicator with annual inflation percentage.
        """
        series_id = _SERIES_MAP["inflation"]
        data = await self._fetch_series(series_id)
        date, value = self._extract_latest(data)
        return EconomicIndicator(
            series_id=series_id,
            name=_SERIES_NAMES[series_id],
            date=date,
            value=value,
        )

    async def get_uma(self) -> EconomicIndicator:
        """Get current UMA (Unidad de Medida y Actualizacion) daily value.

        The UMA is used across Mexican law as a reference unit for fines,
        social security contributions, and tax thresholds.

        Returns:
            EconomicIndicator with daily UMA value in MXN.
        """
        series_id = _SERIES_MAP["uma"]
        data = await self._fetch_series(series_id)
        date, value = self._extract_latest(data)
        return EconomicIndicator(
            series_id=series_id,
            name=_SERIES_NAMES[series_id],
            date=date,
            value=value,
        )
