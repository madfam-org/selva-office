"""Tests for the Tezca legal intelligence adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from madfam_inference.adapters.tezca import (
    ComplianceCheck,
    LawArticle,
    TezcaAdapter,
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


class TestTezcaAdapter:
    """Tezca legal intelligence adapter methods."""

    @pytest.mark.asyncio
    async def test_search_laws_success(self) -> None:
        articles = [
            {
                "ley": "Ley Federal del Trabajo",
                "articulo": "12",
                "titulo": "De las relaciones individuales de trabajo",
                "texto": "Intermediario es la persona que contrata...",
                "vigente": True,
                "fecha_publicacion": "2021-04-23",
            },
            {
                "ley": "Ley Federal del Trabajo",
                "articulo": "13",
                "titulo": "Contratista",
                "texto": "No seran considerados intermediarios...",
                "vigente": True,
                "fecha_publicacion": "2021-04-23",
            },
        ]
        client = _mock_client("get", articles)

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040", token="t")
            result = await adapter.search_laws("subcontratacion", limit=5)

        assert len(result) == 2
        assert isinstance(result[0], LawArticle)
        assert result[0].ley == "Ley Federal del Trabajo"
        assert result[0].articulo == "12"
        assert result[1].articulo == "13"

    @pytest.mark.asyncio
    async def test_search_laws_empty_result(self) -> None:
        client = _mock_client("get", [])

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040", token="t")
            result = await adapter.search_laws("nonexistent_law")

        assert result == []

    @pytest.mark.asyncio
    async def test_search_laws_error_returns_empty(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040")
            result = await adapter.search_laws("anything")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_article_success(self) -> None:
        article_data = {
            "ley": "CFF",
            "articulo": "69-B",
            "titulo": "Presuncion de operaciones inexistentes",
            "texto": "Cuando la autoridad fiscal detecte...",
            "vigente": True,
            "fecha_publicacion": "2014-01-01",
        }
        client = _mock_client("get", article_data)

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040", token="t")
            result = await adapter.get_article("CFF", "69-B")

        assert isinstance(result, LawArticle)
        assert result.ley == "CFF"
        assert result.articulo == "69-B"
        assert "operaciones inexistentes" in result.titulo

    @pytest.mark.asyncio
    async def test_get_article_error_returns_fallback(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040")
            result = await adapter.get_article("LFT", "12")

        assert isinstance(result, LawArticle)
        assert result.ley == "LFT"
        assert result.articulo == "12"
        assert "error" in result.texto

    @pytest.mark.asyncio
    async def test_check_compliance_success(self) -> None:
        compliance_data = {
            "domain": "laboral",
            "compliant": False,
            "issues": ["Missing REPSE registration", "No IMSS records"],
            "recommendations": ["Register REPSE before outsourcing"],
        }
        client = _mock_client("post", compliance_data)

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040", token="t")
            result = await adapter.check_compliance("laboral", context={"rfc": "XAXX010101000"})

        assert isinstance(result, ComplianceCheck)
        assert result.domain == "laboral"
        assert result.compliant is False
        assert len(result.issues) == 2
        assert len(result.recommendations) == 1

    @pytest.mark.asyncio
    async def test_check_compliance_compliant(self) -> None:
        compliance_data = {
            "domain": "fiscal",
            "compliant": True,
            "issues": [],
            "recommendations": [],
        }
        client = _mock_client("post", compliance_data)

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040", token="t")
            result = await adapter.check_compliance("fiscal")

        assert result.compliant is True
        assert result.issues == []

    @pytest.mark.asyncio
    async def test_check_compliance_error_returns_fallback(self) -> None:
        import httpx

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040")
            result = await adapter.check_compliance("mercantil")

        assert isinstance(result, ComplianceCheck)
        assert result.compliant is False
        assert len(result.issues) == 1
        assert "error" in result.issues[0]

    @pytest.mark.asyncio
    async def test_auth_header_propagation(self) -> None:
        client = _mock_client("get", [])

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040", token="my-secret-token")
            await adapter.search_laws("test")

        call_kwargs = client.get.call_args
        headers = call_kwargs[1]["headers"]
        assert headers["Authorization"] == "Bearer my-secret-token"

    @pytest.mark.asyncio
    async def test_no_auth_header_when_token_empty(self) -> None:
        client = _mock_client("get", [])

        with patch(
            "madfam_inference.adapters.tezca.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = TezcaAdapter(base_url="http://tezca:3040", token="")
            await adapter.search_laws("test")

        call_kwargs = client.get.call_args
        headers = call_kwargs[1]["headers"]
        assert "Authorization" not in headers

    @pytest.mark.asyncio
    async def test_default_base_url_from_env(self) -> None:
        with patch.dict(
            "os.environ",
            {"TEZCA_API_URL": "http://custom:9090", "TEZCA_API_TOKEN": "envtok"},
        ):
            adapter = TezcaAdapter()

        assert adapter._base_url == "http://custom:9090"
        assert adapter._token == "envtok"

    def test_trailing_slash_stripped(self) -> None:
        adapter = TezcaAdapter(base_url="http://tezca:3040/")
        assert adapter._base_url == "http://tezca:3040"

    def test_default_values(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            adapter = TezcaAdapter()
        assert "localhost:3040" in adapter._base_url
