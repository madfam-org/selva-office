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


class DeclarationResult(BaseModel):
    declaration_type: str = ""  # "isr_provisional" | "iva_mensual" | "diot"
    period: str = ""
    status: str = ""
    data: dict[str, Any] = {}


class CFDIListItem(BaseModel):
    uuid: str = ""
    emisor_rfc: str = ""
    receptor_rfc: str = ""
    total: str = ""
    fecha: str = ""
    tipo_comprobante: str = ""  # "I" ingreso | "E" egreso | "P" pago


class ConstanciaResult(BaseModel):
    rfc: str = ""
    situacion: str = ""  # "Activo", "Cancelado", etc.
    regimen_fiscal: str = ""
    domicilio_fiscal: str = ""
    fecha_consulta: str = ""


class NOM035Result(BaseModel):
    org_id: str = ""
    survey_type: str = ""
    status: str = ""
    data: dict[str, Any] = {}


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
            base_url or os.environ.get("KARAFIEL_API_URL", "http://localhost:3050")
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

    # -- CFDI listing (period-based) --------------------------------------------

    async def list_cfdis(
        self,
        rfc: str,
        since: str,
        until: str,
    ) -> list[CFDIListItem]:
        """List CFDIs for an RFC within a date range via Karafiel."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/cfdi/list/",
                    headers=self._headers(),
                    params={"rfc": rfc, "since": since, "until": until},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [CFDIListItem(**item) for item in data]
                return []
        except Exception as exc:
            logger.warning("Karafiel CFDI listing failed: %s", exc)
            return []

    # -- Declaration preparation ------------------------------------------------

    async def build_declaration(
        self,
        org_id: str,
        period: str,
        declaration_type: str = "isr_provisional",
        income: float = 0.0,
        expenses: float = 0.0,
        iva_acreditable: float = 0.0,
        iva_trasladado: float = 0.0,
        diot_data: dict[str, Any] | None = None,
    ) -> DeclarationResult:
        """Build a tax declaration via Karafiel fiscal module.

        Args:
            org_id: Organization identifier.
            period: Period string (e.g. ``"2026-04"``).
            declaration_type: One of ``isr_provisional``, ``iva_mensual``, ``diot``.
            income: Total income for the period.
            expenses: Total deductible expenses.
            iva_acreditable: IVA paid on purchases (creditable).
            iva_trasladado: IVA charged on sales (transferred).
            diot_data: DIOT breakdown data (domestic/foreign transactions by RFC).

        Returns:
            DeclarationResult with prepared declaration data.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/fiscal/declarations/build/",
                    headers=self._headers(),
                    json={
                        "org_id": org_id,
                        "period": period,
                        "declaration_type": declaration_type,
                        "income": income,
                        "expenses": expenses,
                        "iva_acreditable": iva_acreditable,
                        "iva_trasladado": iva_trasladado,
                        "diot_data": diot_data or {},
                    },
                )
                resp.raise_for_status()
                return DeclarationResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel declaration build failed: %s", exc)
            return DeclarationResult(
                declaration_type=declaration_type,
                period=period,
                status=f"error: {exc}",
            )

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

    # -- Constancia de Situacion Fiscal -----------------------------------------

    async def get_constancia(self, rfc: str) -> ConstanciaResult:
        """Get Constancia de Situacion Fiscal via Karafiel SAT portal."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/sat/constancia/{rfc}/",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return ConstanciaResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel constancia lookup failed: %s", exc)
            return ConstanciaResult(rfc=rfc, situacion=f"error: {exc}")

    # -- Complemento de Pagos ---------------------------------------------------

    async def generate_complemento_pago(
        self,
        cfdi_uuid: str,
        payment_data: dict[str, Any],
    ) -> CFDIResult:
        """Generate Complemento de Pagos via Karafiel CFDI module."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/cfdi/complemento-pago/",
                    headers=self._headers(),
                    json={"cfdi_uuid": cfdi_uuid, **payment_data},
                )
                resp.raise_for_status()
                return CFDIResult(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel complemento de pago failed: %s", exc)
            return CFDIResult(status=f"error: {exc}")

    # -- NOM-035 Compliance -----------------------------------------------------

    async def generate_nom035_survey(
        self,
        org_id: str,
        survey_type: str = "general",
    ) -> NOM035Result:
        """Generate NOM-035 psychosocial risk survey via Karafiel."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/compliance/nom035/survey/",
                    headers=self._headers(),
                    json={"org_id": org_id, "survey_type": survey_type},
                )
                resp.raise_for_status()
                return NOM035Result(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel NOM-035 survey generation failed: %s", exc)
            return NOM035Result(
                org_id=org_id,
                survey_type=survey_type,
                status=f"error: {exc}",
            )

    # -- Pedimento (customs document) -------------------------------------------

    async def get_pedimento(self, numero: str) -> dict[str, Any]:
        """Look up a customs pedimento document via Karafiel SAT module."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/sat/pedimento/{numero}/",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Karafiel pedimento lookup failed: %s", exc)
            return {"numero": numero, "status": f"error: {exc}"}

    # -- SAT Obligations --------------------------------------------------------

    async def get_sat_obligations(self, rfc: str) -> dict[str, Any]:
        """Check RFC tax obligation status and alerts via Karafiel SAT module."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/sat/obligations/{rfc}/",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Karafiel SAT obligations check failed: %s", exc)
            return {"rfc": rfc, "status": f"error: {exc}"}

    # -- SIEM Compliance --------------------------------------------------------

    async def get_siem_status(self, rfc: str) -> dict[str, Any]:
        """Check SIEM registration status via Karafiel compliance endpoint."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/compliance/siem/{rfc}/",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("Karafiel SIEM status check failed: %s", exc)
            return {"rfc": rfc, "status": f"error: {exc}"}

    # -- NOM-035 Compliance -----------------------------------------------------

    async def generate_nom035_report(
        self,
        org_id: str,
        survey_results: dict[str, Any],
    ) -> NOM035Result:
        """Generate NOM-035 STPS report via Karafiel."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/compliance/nom035/report/",
                    headers=self._headers(),
                    json={"org_id": org_id, "survey_results": survey_results},
                )
                resp.raise_for_status()
                return NOM035Result(**resp.json())
        except Exception as exc:
            logger.warning("Karafiel NOM-035 report generation failed: %s", exc)
            return NOM035Result(
                org_id=org_id,
                status=f"error: {exc}",
            )
