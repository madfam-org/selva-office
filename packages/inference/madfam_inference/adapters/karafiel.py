"""Karafiel compliance adapter -- RFC, CFDI, ISR/IVA, blacklist."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# --- Response Models ---


class RFCValidationResult(BaseModel):
    valid: bool
    rfc: str
    type: str = ""  # "moral" | "fisica"
    name: str = ""
    status: str = ""  # "activo" | "cancelado" | etc.


class CFDIResult(BaseModel):
    uuid: str = ""
    xml: str = ""
    total: str = ""
    status: str = ""


class StampResult(BaseModel):
    folio_fiscal: str = ""
    fecha_timbrado: str = ""
    timbre_xml: str = ""
    status: str = ""


class CFDIStatus(BaseModel):
    uuid: str
    estado: str = ""  # "Vigente" | "Cancelado" | "No Encontrado"
    fecha_cancelacion: str | None = None


class FiscalResult(BaseModel):
    tax_type: str = ""  # "isr" | "iva"
    base_amount: str = ""
    tax_amount: str = ""
    rate: str = ""
    details: dict[str, Any] = {}


class BlacklistResult(BaseModel):
    rfc: str
    listed: bool = False
    article_69b: bool = False
    definitive: bool = False
    details: dict[str, Any] = {}


# --- Adapter ---


class KarafielAdapter:
    """Async client wrapping the Karafiel compliance REST API.

    Uses httpx.AsyncClient for HTTP calls with Bearer token auth.
    All methods return typed Pydantic models and degrade gracefully on error.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("KARAFIEL_API_URL", "http://localhost:3050")
        ).rstrip("/")
        self._token = token or os.environ.get("KARAFIEL_API_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    # -- SAT / RFC ---------------------------------------------------------------

    async def validate_rfc(self, rfc: str) -> RFCValidationResult:
        """Validate RFC via Karafiel SAT module."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/sat/validate-rfc/",
                    headers=self._headers(),
                    json={"rfc": rfc},
                )
                resp.raise_for_status()
                return RFCValidationResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel RFC validation failed: %s", exc)
            return RFCValidationResult(valid=False, rfc=rfc, status=f"error: {exc}")

    # -- CFDI 4.0 ----------------------------------------------------------------

    async def generate_cfdi(
        self,
        emisor_rfc: str,
        receptor_rfc: str,
        conceptos: list[dict[str, Any]],
        forma_pago: str = "01",
        metodo_pago: str = "PUE",
        moneda: str = "MXN",
        tipo_comprobante: str = "I",
    ) -> CFDIResult:
        """Generate CFDI 4.0 XML via Karafiel CFDI module."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/cfdi/generate/",
                    headers=self._headers(),
                    json={
                        "emisor_rfc": emisor_rfc,
                        "receptor_rfc": receptor_rfc,
                        "conceptos": conceptos,
                        "forma_pago": forma_pago,
                        "metodo_pago": metodo_pago,
                        "moneda": moneda,
                        "tipo_comprobante": tipo_comprobante,
                    },
                )
                resp.raise_for_status()
                return CFDIResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel CFDI generation failed: %s", exc)
            return CFDIResult(status=f"error: {exc}")

    async def stamp_cfdi(self, cfdi_xml: str) -> StampResult:
        """Stamp CFDI via PAC through Karafiel."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/cfdi/stamp/",
                    headers=self._headers(),
                    json={"xml": cfdi_xml},
                )
                resp.raise_for_status()
                return StampResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel CFDI stamping failed: %s", exc)
            return StampResult(status=f"error: {exc}")

    async def get_cfdi_status(self, uuid: str) -> CFDIStatus:
        """Check CFDI status via Karafiel."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/cfdi/{uuid}/status/",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return CFDIStatus(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel CFDI status check failed: %s", exc)
            return CFDIStatus(uuid=uuid, estado=f"error: {exc}")

    # -- Fiscal (ISR / IVA) ------------------------------------------------------

    async def compute_isr(
        self,
        income: float,
        period: str = "monthly",
        regime: str = "pf",
    ) -> FiscalResult:
        """Compute ISR via Karafiel fiscal module."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/fiscal/compute/compute-isr/",
                    headers=self._headers(),
                    json={"income": income, "period": period, "regime": regime},
                )
                resp.raise_for_status()
                return FiscalResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel ISR computation failed: %s", exc)
            return FiscalResult(tax_type="isr", details={"error": str(exc)})

    async def compute_iva(
        self,
        amount: float,
        rate: float = 0.16,
        retained: bool = False,
    ) -> FiscalResult:
        """Compute IVA via Karafiel fiscal module."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/fiscal/compute/compute-iva/",
                    headers=self._headers(),
                    json={"amount": amount, "rate": rate, "retained": retained},
                )
                resp.raise_for_status()
                return FiscalResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel IVA computation failed: %s", exc)
            return FiscalResult(tax_type="iva", details={"error": str(exc)})

    # -- Blacklist (Article 69-B) ------------------------------------------------

    async def check_blacklist(self, rfc: str) -> BlacklistResult:
        """Check Article 69-B blacklist via Karafiel."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/blacklist/check/",
                    headers=self._headers(),
                    json={"rfc": rfc},
                )
                resp.raise_for_status()
                return BlacklistResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel blacklist check failed: %s", exc)
            return BlacklistResult(rfc=rfc, details={"error": str(exc)})
