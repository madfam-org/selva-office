"""MADFAM Crawler adapter -- web scraping as a service."""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# --- Response Models ---


class CrawlJob(BaseModel):
    job_id: str = ""
    status: str = ""  # "queued" | "running" | "completed" | "failed"
    results: list[dict[str, Any]] = []


class DOFEntry(BaseModel):
    title: str = ""
    date: str = ""
    url: str = ""
    summary: str = ""
    section: str = ""


# --- Adapter ---


class CrawlerAdapter:
    """Async client wrapping the MADFAM Crawler REST API.

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
            or os.environ.get("CRAWLER_API_URL", "http://localhost:3070")
        ).rstrip("/")
        self._token = token or os.environ.get("CRAWLER_API_TOKEN", "")

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {"Content-Type": "application/json"}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        return h

    # -- Generic scraping -------------------------------------------------------

    async def submit_scrape(
        self,
        url: str,
        selectors: dict[str, str] | None = None,
    ) -> CrawlJob:
        """Submit a scrape job to the MADFAM Crawler.

        Args:
            url: Target URL to scrape.
            selectors: Optional CSS/XPath selectors for structured extraction.

        Returns:
            CrawlJob with job_id and initial status.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/jobs",
                    headers=self._headers(),
                    json={"url": url, "selectors": selectors or {}},
                )
                resp.raise_for_status()
                return CrawlJob(**resp.json())
        except Exception as exc:
            logger.warning("Crawler submit_scrape failed: %s", exc)
            return CrawlJob(status=f"error: {exc}")

    async def get_job_status(self, job_id: str) -> CrawlJob:
        """Poll the status of a crawl job.

        Args:
            job_id: The job identifier returned by submit_scrape.

        Returns:
            CrawlJob with current status and results if completed.
        """
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"{self._base_url}/api/v1/jobs/{job_id}",
                    headers=self._headers(),
                )
                resp.raise_for_status()
                return CrawlJob(**resp.json())
        except Exception as exc:
            logger.warning("Crawler get_job_status failed: %s", exc)
            return CrawlJob(job_id=job_id, status=f"error: {exc}")

    # -- DOF (Diario Oficial de la Federacion) -----------------------------------

    async def search_dof(
        self,
        query: str,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search the Diario Oficial de la Federacion for regulatory changes.

        Args:
            query: Search terms (e.g. 'reforma fiscal', 'RESICO').
            since: Optional ISO date string to filter results after this date.

        Returns:
            List of matching DOF entries as dicts.
        """
        try:
            body: dict[str, Any] = {"query": query}
            if since:
                body["since"] = since
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{self._base_url}/api/v1/dof/search",
                    headers=self._headers(),
                    json=body,
                )
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "results" in data:
                    return data["results"]
                return []
        except Exception as exc:
            logger.warning("Crawler DOF search failed: %s", exc)
            return []
