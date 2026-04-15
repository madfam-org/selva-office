"""Tezca legal intelligence adapter -- Mexican law search and compliance."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# --- Response Models ---


class LawArticle(BaseModel):
    ley: str = ""
    articulo: str = ""
    titulo: str = ""
    texto: str = ""
    vigente: bool = True
    fecha_publicacion: str = ""


class ComplianceCheck(BaseModel):
    domain: str = ""
    compliant: bool = True
    issues: list[str] = []
    recommendations: list[str] = []


# --- Adapter ---


class TezcaAdapter:
    """Async client wrapping the Tezca legal intelligence REST API.

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
            or os.environ.get("TEZCA_API_URL", "http://localhost:3040")
        ).rstrip("/")
        self._token = token or os.environ.get("TEZCA_API_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    # -- Law Search ---------------------------------------------------------------

    async def search_laws(self, query: str, limit: int = 10) -> list[LawArticle]:
        """Search Mexican laws by keyword via Tezca search endpoint."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/laws/search",
                    headers=self._headers(),
                    params={"q": query, "limit": limit},
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [LawArticle(**item) for item in data]
                return []
        except Exception as exc:
            logger.warning("Tezca law search failed: %s", exc)
            return []

    # -- Article Lookup -----------------------------------------------------------

    async def get_article(self, ley: str, articulo: str) -> LawArticle:
        """Get a specific law article by statute and article number."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/laws/{ley}/articles/{articulo}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return LawArticle(**resp.json())
        except Exception as exc:
            logger.warning("Tezca article lookup failed: %s", exc)
            return LawArticle(ley=ley, articulo=articulo, texto=f"error: {exc}")

    # -- Compliance Check ---------------------------------------------------------

    async def check_compliance(
        self,
        domain: str,
        context: dict[str, Any] | None = None,
    ) -> ComplianceCheck:
        """Run a regulatory compliance check for a business domain.

        Args:
            domain: Compliance domain (laboral, fiscal, mercantil, datos_personales).
            context: Additional context for the compliance evaluation.

        Returns:
            ComplianceCheck with compliance status and recommendations.
        """
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/compliance/check",
                    headers=self._headers(),
                    json={"domain": domain, "context": context or {}},
                )
                resp.raise_for_status()
                return ComplianceCheck(**resp.json())
        except Exception as exc:
            logger.warning("Tezca compliance check failed: %s", exc)
            return ComplianceCheck(
                domain=domain,
                compliant=False,
                issues=[f"error: {exc}"],
            )
