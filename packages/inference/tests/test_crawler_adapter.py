"""Tests for the MADFAM Crawler adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from madfam_inference.adapters.crawler import CrawlerAdapter, CrawlJob


def _mock_response(data: dict | list) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


def _mock_client(method: str = "post", data: dict | list | None = None) -> AsyncMock:
    """Return an AsyncMock httpx client with the specified method mocked."""
    mock_client = AsyncMock()
    getattr(mock_client, method).return_value = _mock_response(data or {})
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    return mock_client


class TestCrawlerAdapterInit:
    """CrawlerAdapter constructor and configuration."""

    def test_default_base_url(self) -> None:
        adapter = CrawlerAdapter()
        assert adapter._base_url == "http://localhost:3070"

    def test_custom_base_url(self) -> None:
        adapter = CrawlerAdapter(base_url="http://crawler:9090")
        assert adapter._base_url == "http://crawler:9090"

    def test_trailing_slash_stripped(self) -> None:
        adapter = CrawlerAdapter(base_url="http://crawler:3070/")
        assert adapter._base_url == "http://crawler:3070"

    def test_env_override(self) -> None:
        with patch.dict(
            "os.environ",
            {"CRAWLER_API_URL": "http://custom:8080", "CRAWLER_API_TOKEN": "tok"},
        ):
            adapter = CrawlerAdapter()
        assert adapter._base_url == "http://custom:8080"
        assert adapter._token == "tok"

    def test_auth_header_present_when_token_set(self) -> None:
        adapter = CrawlerAdapter(token="my-token")
        headers = adapter._headers()
        assert headers["Authorization"] == "Bearer my-token"

    def test_no_auth_header_when_token_empty(self) -> None:
        adapter = CrawlerAdapter(token="")
        headers = adapter._headers()
        assert "Authorization" not in headers


class TestSubmitScrape:
    """submit_scrape() calls POST /api/v1/jobs."""

    @pytest.mark.asyncio
    async def test_submit_scrape_success(self) -> None:
        client = _mock_client(
            "post",
            {
                "job_id": "job-123",
                "status": "queued",
                "results": [],
            },
        )

        with patch(
            "madfam_inference.adapters.crawler.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = CrawlerAdapter(base_url="http://crawler:3070", token="t")
            result = await adapter.submit_scrape("https://example.com", selectors={"title": "h1"})

        assert isinstance(result, CrawlJob)
        assert result.job_id == "job-123"
        assert result.status == "queued"

    @pytest.mark.asyncio
    async def test_submit_scrape_error_graceful(self) -> None:
        import httpx

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.crawler.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = CrawlerAdapter()
            result = await adapter.submit_scrape("https://example.com")

        assert isinstance(result, CrawlJob)
        assert "error" in result.status


class TestGetJobStatus:
    """get_job_status() calls GET /api/v1/jobs/{job_id}."""

    @pytest.mark.asyncio
    async def test_get_job_status_completed(self) -> None:
        client = _mock_client(
            "get",
            {
                "job_id": "job-456",
                "status": "completed",
                "results": [{"title": "Page Title", "content": "text"}],
            },
        )

        with patch(
            "madfam_inference.adapters.crawler.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = CrawlerAdapter(base_url="http://crawler:3070", token="t")
            result = await adapter.get_job_status("job-456")

        assert isinstance(result, CrawlJob)
        assert result.status == "completed"
        assert len(result.results) == 1

    @pytest.mark.asyncio
    async def test_get_job_status_error_graceful(self) -> None:
        import httpx

        client = AsyncMock()
        client.get.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.crawler.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = CrawlerAdapter()
            result = await adapter.get_job_status("job-999")

        assert isinstance(result, CrawlJob)
        assert result.job_id == "job-999"
        assert "error" in result.status


class TestSearchDOF:
    """search_dof() calls POST /api/v1/dof/search."""

    @pytest.mark.asyncio
    async def test_search_dof_returns_list(self) -> None:
        entries = [
            {"title": "Reforma Fiscal 2026", "date": "2026-04-10", "url": "https://dof.gob.mx/1"},
            {"title": "Salario Minimo", "date": "2026-04-12", "url": "https://dof.gob.mx/2"},
        ]
        client = _mock_client("post", entries)

        with patch(
            "madfam_inference.adapters.crawler.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = CrawlerAdapter(base_url="http://crawler:3070", token="t")
            results = await adapter.search_dof("reforma fiscal", since="2026-01-01")

        assert len(results) == 2
        assert results[0]["title"] == "Reforma Fiscal 2026"

    @pytest.mark.asyncio
    async def test_search_dof_with_results_wrapper(self) -> None:
        """API may wrap results in a dict with 'results' key."""
        client = _mock_client(
            "post",
            {
                "results": [{"title": "Entry 1"}],
                "total": 1,
            },
        )

        with patch(
            "madfam_inference.adapters.crawler.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = CrawlerAdapter()
            results = await adapter.search_dof("RESICO")

        assert len(results) == 1
        assert results[0]["title"] == "Entry 1"

    @pytest.mark.asyncio
    async def test_search_dof_error_returns_empty(self) -> None:
        import httpx

        client = AsyncMock()
        client.post.side_effect = httpx.ConnectError("Connection refused")
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "madfam_inference.adapters.crawler.httpx.AsyncClient",
            return_value=client,
        ):
            adapter = CrawlerAdapter()
            results = await adapter.search_dof("reforma fiscal")

        assert results == []
