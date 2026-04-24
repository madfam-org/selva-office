"""HTTP tools: generic requests, GraphQL queries, and webhook delivery."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import socket
import urllib.parse
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger("autoswarm.http_tools")

# ---------------------------------------------------------------------------
# SSRF protection -- mirrors the gateway.py _validate_webhook_url pattern
# ---------------------------------------------------------------------------
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
]


def _validate_url(url: str) -> str:
    """Validate a URL to prevent SSRF attacks.

    Checks:
    - Length <= 2048 characters
    - Scheme must be http or https
    - Hostname must resolve to a non-private IP address

    Returns the validated URL, or raises ValueError on failure.
    """
    if len(url) > 2048:
        raise ValueError("URL exceeds maximum length of 2048 characters")

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL scheme must be http or https, got: {parsed.scheme}")

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL is missing a hostname")

    try:
        addrinfos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"Hostname could not be resolved: {hostname}") from exc

    for _family, _type, _proto, _canonname, sockaddr in addrinfos:
        ip = ipaddress.ip_address(sockaddr[0])
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                raise ValueError(f"Hostname resolves to a private/reserved IP address: {hostname}")

    return url


class HTTPRequestTool(BaseTool):
    name = "http_request"
    description = (
        "Make an HTTP request to an external URL. "
        "Supports GET, POST, PUT, DELETE methods. "
        "SSRF protection blocks requests to private IP ranges."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target URL",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "default": "GET",
                    "description": "HTTP method",
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers as key-value pairs",
                    "default": {},
                },
                "body": {
                    "description": "Request body (string or JSON object)",
                    "default": None,
                },
                "timeout": {
                    "type": "integer",
                    "description": "Request timeout in seconds",
                    "default": 30,
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import httpx

        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET").upper()
        headers = kwargs.get("headers", {}) or {}
        body = kwargs.get("body")
        timeout = kwargs.get("timeout", 30)

        try:
            validated_url = _validate_url(url)
        except ValueError as exc:
            return ToolResult(success=False, error=f"URL validation failed: {exc}")

        try:
            async with httpx.AsyncClient(timeout=float(timeout)) as client:
                request_kwargs: dict[str, Any] = {
                    "method": method,
                    "url": validated_url,
                    "headers": headers,
                }
                if body is not None:
                    if isinstance(body, dict):
                        request_kwargs["json"] = body
                    else:
                        request_kwargs["content"] = str(body)

                resp = await client.request(**request_kwargs)

            resp_body = resp.text[:50000]  # Cap response size
            resp_headers = dict(resp.headers)

            return ToolResult(
                output=f"HTTP {resp.status_code} {method} {url}\n{resp_body[:2000]}",
                data={
                    "status_code": resp.status_code,
                    "headers": resp_headers,
                    "body": resp_body,
                    "url": str(resp.url),
                },
            )
        except Exception as exc:
            logger.error("http_request failed: %s", exc)
            return ToolResult(success=False, error=str(exc))


class GraphQLQueryTool(BaseTool):
    name = "graphql_query"
    description = (
        "Execute a GraphQL query against a remote endpoint. "
        "SSRF protection blocks requests to private IP ranges."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "GraphQL endpoint URL",
                },
                "query": {
                    "type": "string",
                    "description": "GraphQL query string",
                },
                "variables": {
                    "type": "object",
                    "description": "Query variables",
                    "default": {},
                },
                "headers": {
                    "type": "object",
                    "description": "Request headers",
                    "default": {},
                },
            },
            "required": ["url", "query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import httpx

        url = kwargs.get("url", "")
        query = kwargs.get("query", "")
        variables = kwargs.get("variables", {}) or {}
        headers = kwargs.get("headers", {}) or {}

        try:
            validated_url = _validate_url(url)
        except ValueError as exc:
            return ToolResult(success=False, error=f"URL validation failed: {exc}")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    validated_url,
                    json={"query": query, "variables": variables},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            if "errors" in data and data["errors"]:
                error_msgs = "; ".join(e.get("message", "") for e in data["errors"])
                return ToolResult(
                    output=f"GraphQL errors: {error_msgs}",
                    data=data,
                )

            return ToolResult(
                output="GraphQL query returned data",
                data=data,
            )
        except Exception as exc:
            logger.error("graphql_query failed: %s", exc)
            return ToolResult(success=False, error=str(exc))


class WebhookSendTool(BaseTool):
    name = "webhook_send"
    description = (
        "Send a JSON payload to a webhook URL. "
        "Optionally signs the payload with HMAC-SHA256 in X-Signature header. "
        "SSRF protection blocks requests to private IP ranges."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Webhook target URL",
                },
                "payload": {
                    "type": "object",
                    "description": "JSON payload to send",
                },
                "secret": {
                    "type": "string",
                    "description": "Optional HMAC-SHA256 signing secret",
                    "default": "",
                },
            },
            "required": ["url", "payload"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        import json

        import httpx

        url = kwargs.get("url", "")
        payload = kwargs.get("payload", {})
        secret = kwargs.get("secret", "")

        try:
            validated_url = _validate_url(url)
        except ValueError as exc:
            return ToolResult(success=False, error=f"URL validation failed: {exc}")

        headers: dict[str, str] = {"Content-Type": "application/json"}
        body_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        if secret:
            signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
            headers["X-Signature"] = f"sha256={signature}"

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    validated_url,
                    content=body_bytes,
                    headers=headers,
                )

            return ToolResult(
                output=f"Webhook sent to {url}: HTTP {resp.status_code}",
                data={
                    "status_code": resp.status_code,
                    "url": url,
                    "signed": bool(secret),
                },
            )
        except Exception as exc:
            logger.error("webhook_send failed: %s", exc)
            return ToolResult(success=False, error=str(exc))
