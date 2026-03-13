"""Web tools: search, fetch, scrape."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web using a query (requires TAVILY_API_KEY or falls back to stub)"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import os

        query = kwargs.get("query", "")
        max_results = kwargs.get("max_results", 5)
        api_key = os.environ.get("TAVILY_API_KEY")

        if not api_key:
            return ToolResult(
                output=f"Web search for '{query}' — no TAVILY_API_KEY configured",
                data={"results": [], "query": query},
            )

        import httpx

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": max_results,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                output = "\n".join(
                    f"- {r.get('title', '')}: {r.get('url', '')}" for r in results
                )
                return ToolResult(output=output, data={"results": results})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch the content of a URL"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to fetch"},
                "max_length": {
                    "type": "integer",
                    "description": "Max response length in chars",
                    "default": 10000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import httpx

        url = kwargs.get("url", "")
        max_length = kwargs.get("max_length", 10000)
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                text = resp.text[:max_length]
                return ToolResult(
                    output=text,
                    data={"status_code": resp.status_code, "url": str(resp.url)},
                )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class WebScrapeTool(BaseTool):
    name = "web_scrape"
    description = "Fetch a URL and extract text content (strips HTML tags)"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL to scrape"},
                "max_length": {"type": "integer", "default": 10000},
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import html
        import re

        import httpx

        url = kwargs.get("url", "")
        max_length = kwargs.get("max_length", 10000)
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                # Simple HTML tag stripping
                text = re.sub(r"<[^>]+>", "", resp.text)
                text = html.unescape(text)
                # Collapse whitespace
                text = re.sub(r"\s+", " ", text).strip()[:max_length]
                return ToolResult(output=text)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
