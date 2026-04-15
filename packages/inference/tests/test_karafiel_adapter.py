"""Tests for the Karafiel compliance adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from madfam_inference.adapters.karafiel import (
    BlacklistResult,
    CFDIResult,
    CFDIStatus,
    ConstanciaResult,
    FiscalResult,
    KarafielAdapter,
    NOM035Result,
    RFCValidationResult,
    StampResult,
)


def _mock_response(data: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


def _mock_client(method: str = "post", data: dict | None = None) -> AsyncMock:
    """Return an AsyncMock httpx client with the specified method mocked."""
    mock_client = AsyncMock()
    getattr(mock_client, method).return_value = _mock_response(data or {})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestKarafielAdapter:
    """Karafiel compliance adapter methods."""

    @pytest.mark.asyncio
    async def test_validate_rfc_success(self) -> None:
        client = _mock_client("post", {
            "valid": True,
            "rfc": "XAXX010101000",
            "type": "moral",
            "name": "Empresa SA de CV",
            "status": "activo",
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.validate_rfc("XAXX010101000")

        assert isinstance(result, RFCValidationResult)
        assert result.valid is True
        assert result.rfc == "XAXX010101000"
        assert result.type == "moral"

    @pytest.mark.asyncio
    async def test_validate_rfc_error_returns_graceful_fallback(self) -> None:
        import httpx

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050")
            result = await adapter.validate_rfc("BAD_RFC")

        assert isinstance(result, RFCValidationResult)
        assert result.valid is False
        assert "error" in result.status

    @pytest.mark.asyncio
    async def test_generate_cfdi(self) -> None:
        client = _mock_client("post", {
            "uuid": "abc-123-def",
            "xml": "<cfdi>...</cfdi>",
            "total": "1160.00",
            "status": "generated",
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.generate_cfdi(
                emisor_rfc="EMISOR010101AAA",
                receptor_rfc="RECEP020202BBB",
                conceptos=[{"descripcion": "Servicio", "valor_unitario": 1000.0}],
            )

        assert isinstance(result, CFDIResult)
        assert result.uuid == "abc-123-def"
        assert result.total == "1160.00"

    @pytest.mark.asyncio
    async def test_stamp_cfdi(self) -> None:
        client = _mock_client("post", {
            "folio_fiscal": "FF-001",
            "fecha_timbrado": "2026-04-14T10:00:00",
            "timbre_xml": "<timbre>...</timbre>",
            "status": "stamped",
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.stamp_cfdi("<cfdi>...</cfdi>")

        assert isinstance(result, StampResult)
        assert result.folio_fiscal == "FF-001"

    @pytest.mark.asyncio
    async def test_get_cfdi_status(self) -> None:
        client = _mock_client("get", {
            "uuid": "abc-123-def",
            "estado": "Vigente",
            "fecha_cancelacion": None,
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.get_cfdi_status("abc-123-def")

        assert isinstance(result, CFDIStatus)
        assert result.estado == "Vigente"
        assert result.fecha_cancelacion is None

    @pytest.mark.asyncio
    async def test_compute_isr(self) -> None:
        client = _mock_client("post", {
            "tax_type": "isr",
            "base_amount": "50000.00",
            "tax_amount": "8500.00",
            "rate": "0.17",
            "details": {"bracket": 4},
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.compute_isr(income=50000.0, period="monthly")

        assert isinstance(result, FiscalResult)
        assert result.tax_type == "isr"
        assert result.tax_amount == "8500.00"

    @pytest.mark.asyncio
    async def test_compute_iva(self) -> None:
        client = _mock_client("post", {
            "tax_type": "iva",
            "base_amount": "10000.00",
            "tax_amount": "1600.00",
            "rate": "0.16",
            "details": {},
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.compute_iva(amount=10000.0, rate=0.16)

        assert isinstance(result, FiscalResult)
        assert result.tax_type == "iva"
        assert result.tax_amount == "1600.00"

    @pytest.mark.asyncio
    async def test_check_blacklist(self) -> None:
        client = _mock_client("post", {
            "rfc": "MALR800101AAA",
            "listed": True,
            "article_69b": True,
            "definitive": False,
            "details": {"date_listed": "2025-06-01"},
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.check_blacklist("MALR800101AAA")

        assert isinstance(result, BlacklistResult)
        assert result.listed is True
        assert result.article_69b is True
        assert result.definitive is False

    @pytest.mark.asyncio
    async def test_get_constancia(self) -> None:
        client = _mock_client("get", {
            "rfc": "XAXX010101000",
            "situacion": "Activo",
            "regimen_fiscal": "601 - General de Ley Personas Morales",
            "domicilio_fiscal": "CDMX",
            "fecha_consulta": "2026-04-14",
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.get_constancia("XAXX010101000")

        assert isinstance(result, ConstanciaResult)
        assert result.situacion == "Activo"
        assert result.regimen_fiscal == "601 - General de Ley Personas Morales"

    @pytest.mark.asyncio
    async def test_get_constancia_error_returns_graceful_fallback(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050")
            result = await adapter.get_constancia("BAD_RFC")

        assert isinstance(result, ConstanciaResult)
        assert "error" in result.situacion

    @pytest.mark.asyncio
    async def test_generate_complemento_pago(self) -> None:
        client = _mock_client("post", {
            "uuid": "comp-pago-uuid-001",
            "xml": "<cfdi:complemento>...</cfdi:complemento>",
            "total": "5000.00",
            "status": "generated",
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.generate_complemento_pago(
                cfdi_uuid="original-cfdi-uuid",
                payment_data={
                    "monto_pagado": "5000.00",
                    "fecha_pago": "2026-04-14",
                    "forma_pago": "03",
                },
            )

        assert isinstance(result, CFDIResult)
        assert result.uuid == "comp-pago-uuid-001"
        assert result.status == "generated"

    @pytest.mark.asyncio
    async def test_generate_complemento_pago_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050")
            result = await adapter.generate_complemento_pago("uuid", {})

        assert isinstance(result, CFDIResult)
        assert "error" in result.status

    @pytest.mark.asyncio
    async def test_generate_nom035_survey(self) -> None:
        client = _mock_client("post", {
            "org_id": "org-123",
            "survey_type": "general",
            "status": "generated",
            "data": {"questions": 72, "categories": 5},
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.generate_nom035_survey("org-123", "general")

        assert isinstance(result, NOM035Result)
        assert result.status == "generated"
        assert result.data["questions"] == 72

    @pytest.mark.asyncio
    async def test_generate_nom035_survey_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050")
            result = await adapter.generate_nom035_survey("org-123")

        assert isinstance(result, NOM035Result)
        assert "error" in result.status

    @pytest.mark.asyncio
    async def test_generate_nom035_report(self) -> None:
        client = _mock_client("post", {
            "org_id": "org-123",
            "survey_type": "",
            "status": "completed",
            "data": {"risk_level": "medio", "recommendations": 3},
        })

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="t")
            result = await adapter.generate_nom035_report(
                "org-123",
                {"responses": [1, 2, 3]},
            )

        assert isinstance(result, NOM035Result)
        assert result.status == "completed"
        assert result.data["risk_level"] == "medio"

    @pytest.mark.asyncio
    async def test_generate_nom035_report_error(self) -> None:
        import httpx

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050")
            result = await adapter.generate_nom035_report("org-123", {})

        assert isinstance(result, NOM035Result)
        assert "error" in result.status

    @pytest.mark.asyncio
    async def test_auth_header_propagation(self) -> None:
        client = _mock_client("post", {"valid": True, "rfc": "X"})

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(
                base_url="http://karafiel:3050", token="my-secret-token"
            )
            await adapter.validate_rfc("X")

        call_kwargs = client.post.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["Authorization"] == "Bearer my-secret-token"

    @pytest.mark.asyncio
    async def test_no_auth_header_when_token_empty(self) -> None:
        client = _mock_client("post", {"valid": False, "rfc": "X"})

        with patch(
            "madfam_inference.adapters.karafiel.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = KarafielAdapter(base_url="http://karafiel:3050", token="")
            await adapter.validate_rfc("X")

        call_kwargs = client.post.call_args
        headers = call_kwargs[1]["headers"]
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_default_base_url_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {"KARAFIEL_API_URL": "http://custom:9090", "KARAFIEL_API_TOKEN": "envtok"},
        ):
            adapter = KarafielAdapter()

        assert adapter._base_url == "http://custom:9090"
        assert adapter._token == "envtok"

    def test_trailing_slash_stripped(self) -> None:
        adapter = KarafielAdapter(base_url="http://karafiel:3050/")
        assert adapter._base_url == "http://karafiel:3050"
