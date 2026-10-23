"""Karafiel compliance adapter -- RFC, CFDI, ISR/IVA, blacklist."""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import httpx
from pydantic import BaseModel, StrictBool

from .financial_reads import FinancialReadUnavailableError

logger = logging.getLogger(__name__)


# --- Response Models ---


class RFCValidationResult(BaseModel):
    valid: StrictBool
    rfc: str
    type: str = ""  # "moral" | "fisica"
    name: str = ""
    status: str = ""  # "activo" | "cancelado" | etc.
    check_status: Literal["checked", "unknown"] = "unknown"

    @property
    def check_completed(self) -> bool:
        """The source returned a verdict; this is not broader tax clearance."""
        status = self.status.strip().lower()
        return (
            self.check_status == "checked"
            and type(self.valid) is bool
            and status not in {"unknown", "unavailable"}
            and not status.startswith("error")
        )


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
    listed: StrictBool | None = None
    article_69b: StrictBool | None = None
    definitive: StrictBool | None = None
    check_status: Literal["checked", "unknown"] = "unknown"
    details: dict[str, Any] = {}

    @property
    def check_completed(self) -> bool:
        """A completed lookup is not a tax-clearance or source-freshness verdict."""
        return (
            self.check_status == "checked"
            and self.listed is not None
            and self.article_69b is not None
            and self.definitive is not None
            and not self.details.get("error")
            and not (self.article_69b and not self.listed)
            and not (self.definitive and not self.article_69b)
        )


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
        """Return a subject-bound verdict or an explicit unknown lookup."""
        try:
            if not self._base_url or not self._token or not rfc.strip():
                raise ValueError("Validation source or subject unavailable")
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/sat/validate-rfc/",
                    headers=self._headers(),
                    json={"rfc": rfc},
                )
                resp.raise_for_status()
                payload = resp.json()
                if (
                    not isinstance(payload, dict)
                    or "error" in payload
                    or ("success" in payload and payload["success"] is not True)
                    or payload.get("check_status", "checked") != "checked"
                ):
                    raise ValueError("Validation response unavailable")
                result = RFCValidationResult(**{**payload, "check_status": "checked"})
                if result.rfc != rfc or not result.check_completed:
                    raise ValueError("Validation response incomplete or subject mismatch")
                return result
        except Exception:
            logger.warning("Karafiel RFC validation unavailable")
            return RFCValidationResult(valid=False, rfc=rfc, status="unavailable")

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
        """Refuse the unimplemented legacy history contract.

        The real collection is scoped by the authenticated active taxpayer and
        does not implement these date arguments. Calling it with an arbitrary
        RFC/date query could silently return the wrong scope or period. A new
        adapter needs verified scope, paging and history coverage before use.
        """
        raise FinancialReadUnavailableError("karafiel_cfdi_history_contract_unavailable")

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
        """Read an explicit screening result; unavailable is never unlisted.

        Do not silently substitute Karafiel's metered clearance mutation for
        this lookup contract. A missing endpoint must remain unknown until the
        integration contract is implemented and verified.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/blacklist/check/",
                    headers=self._headers(),
                    json={"rfc": rfc},
                )
                resp.raise_for_status()
                payload = resp.json()
                if not isinstance(payload, dict) or payload.get("error"):
                    raise ValueError("Invalid blacklist response")
                result = BlacklistResult(**payload)
                # Require every boolean and the exact requested subject. A
                # partial/error envelope must not acquire defaults of False.
                if (
                    result.rfc != rfc
                    or payload.get("check_status", "checked") != "checked"
                    or payload.get("status", "checked") != "checked"
                    or any(
                        type(payload.get(field)) is not bool
                        for field in ("listed", "article_69b", "definitive")
                    )
                ):
                    raise ValueError("Incomplete blacklist response")
                result.check_status = "checked"
                if not result.check_completed:
                    raise ValueError("Inconsistent blacklist response")
                return result
        except Exception:
            # HTTP/validation exceptions may contain taxpayer data, request
            # bodies or credentials. Emit only a stable, non-sensitive reason.
            logger.warning("Karafiel blacklist lookup unavailable or invalid")
            return BlacklistResult(rfc=rfc, details={"error": "blacklist_lookup_unavailable"})

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
