"""``POST /mcp`` — Selva's native COGS MCP (RFC 0051 Phase A).

Real RS256 tokens signed with a throwaway key go through ``auth.verify_jwt``;
only the JWKS fetch is patched. Synthetic orgs and clients only.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import jsonschema
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api import auth as auth_mod
from nexus_api.config import get_settings
from nexus_api.mcp import protocol
from nexus_api.mcp.router import rate_limiter
from nexus_api.mcp.tools import TOOLS
from nexus_api.models import ComputeTokenLedger

_ISSUER = "https://janua.test"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key())) | {
    "kid": "mcp-test",
    "alg": "RS256",
    "use": "sig",
}
_CLIENT = "synthetic-ops-agent"


def _token(**overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "sub": f"service-account:{_CLIENT}",
        "client_id": _CLIENT,
        "scope": "openid selva-cogs:read",
        "token_use": "client_credentials",
        "org_id": "org-a",
        "iss": _ISSUER,
        "aud": get_settings().janua_client_id,
        "iat": now,
        "exp": now + 600,
    }
    for name, value in overrides.items():
        if value is None:
            claims.pop(name, None)
        else:
            claims[name] = value
    return jwt.encode(claims, _KEY, algorithm="RS256", headers={"kid": "mcp-test"})


@pytest.fixture(autouse=True)
def _mcp_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    settings = get_settings()
    monkeypatch.setattr(settings, "selva_mcp_enabled", True)
    monkeypatch.setattr(settings, "janua_issuer_url", _ISSUER)
    monkeypatch.setattr(settings, "selva_mcp_rate_per_minute", 60)
    rate_limiter.reset()
    with patch.object(auth_mod, "_fetch_jwks", AsyncMock(return_value={"keys": [_JWK]})):
        yield
    rate_limiter.reset()


def _rpc(method: str, params: dict[str, Any] | None = None, rid: int = 1) -> dict[str, Any]:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": rid, "method": method}
    if params is not None:
        message["params"] = params
    return message


async def _post(
    client: httpx.AsyncClient, body: Any, token: str | None = None, **headers: str
) -> httpx.Response:
    sent = {"Content-Type": "application/json", **headers}
    if token is not None:
        sent["Authorization"] = f"Bearer {token}"
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return await client.post("/mcp", content=raw, headers=sent)


def _call(org: str = "org-a", month: str = "2026-09") -> dict[str, Any]:
    return _rpc(
        "tools/call", {"name": "inference_usage", "arguments": {"org": org, "month": month}}
    )


async def _seed(db: AsyncSession) -> None:
    at = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
    db.add_all(
        [
            ComputeTokenLedger(
                org_id="org-a",
                action="inference_proxy",
                amount=1200,
                cost_usd=Decimal("0.012000"),
                caller="service-account:synthetic-quoting",
                provider="anthropic",
                model="claude-haiku-4-5",
                created_at=at,
            ),
            ComputeTokenLedger(
                org_id="org-b",
                action="inference_proxy",
                amount=99999,
                cost_usd=Decimal("9.000000"),
                caller="service-account:synthetic-other",
                provider="openai",
                model="gpt-4o",
                created_at=at,
            ),
        ]
    )
    await db.commit()


class TestSwitch:
    async def test_off_answers_404_before_auth(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "selva_mcp_enabled", False)
        assert (await _post(client, _rpc("tools/list"))).status_code == 404
        assert (await _post(client, _rpc("tools/list"), _token())).status_code == 404
        assert (await client.get("/mcp")).status_code == 404

    def test_switch_defaults_off(self) -> None:
        from nexus_api.config import Settings

        assert Settings.model_fields["selva_mcp_enabled"].default is False

    async def test_get_is_405_when_on(self, client: httpx.AsyncClient) -> None:
        assert (await client.get("/mcp")).status_code == 405


class TestAuth:
    async def test_missing_token_is_401(self, client: httpx.AsyncClient) -> None:
        assert (await _post(client, _rpc("tools/list"))).status_code == 401

    async def test_bad_signature_is_401(self, client: httpx.AsyncClient) -> None:
        other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode(
            {"sub": "service-account:x", "iss": _ISSUER, "aud": "selva-office", "exp": 9e9},
            other,
            algorithm="RS256",
            headers={"kid": "mcp-test"},
        )
        assert (await _post(client, _rpc("tools/list"), forged)).status_code == 401

    async def test_wrong_audience_is_401(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("tools/list"), _token(aud="another-api"))
        assert resp.status_code == 401

    async def test_worker_shared_secret_refused(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(get_settings(), "worker_api_token", "synthetic-worker-secret")
        resp = await _post(client, _rpc("tools/list"), "synthetic-worker-secret")
        assert resp.status_code == 401

    async def test_missing_scope_is_403(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("tools/list"), _token(scope="openid selva-cogs:write"))
        assert resp.status_code == 403
        assert "selva-cogs:read" in resp.json()["detail"]

    async def test_no_scope_claim_is_403(self, client: httpx.AsyncClient) -> None:
        assert (await _post(client, _rpc("tools/list"), _token(scope=None))).status_code == 403

    async def test_person_token_is_403(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("tools/list"), _token(sub="person-subject-1"))
        assert resp.status_code == 403

    async def test_client_without_org_is_403(self, client: httpx.AsyncClient) -> None:
        assert (await _post(client, _rpc("tools/list"), _token(org_id=None))).status_code == 403

    async def test_browser_origin_is_403(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("tools/list"), _token(), Origin="https://evil.test")
        assert resp.status_code == 403


class TestProtocol:
    async def test_initialize(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("initialize", {"protocolVersion": "2025-06-18"}), _token())
        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["protocolVersion"] == "2025-06-18"
        assert result["capabilities"] == {"tools": {"listChanged": False}}
        assert "LIST-PRICE ESTIMATES" in result["instructions"]

    async def test_tools_list_names_and_titles(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("tools/list"), _token())
        tools = resp.json()["result"]["tools"]
        assert [t["name"] for t in tools] == ["inference_usage"]
        assert tools[0]["title"] == "inference.usage"
        assert tools[0]["annotations"]["readOnlyHint"] is True
        assert tools[0]["inputSchema"]["required"] == ["org", "month"]

    def test_tool_names_are_loadable_by_claude(self) -> None:
        import re

        assert all(re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", name) for name in TOOLS)

    async def test_notification_is_202(self, client: httpx.AsyncClient) -> None:
        body = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        resp = await _post(client, body, _token())
        assert resp.status_code == 202 and resp.content == b""

    async def test_parse_error_and_batch(self, client: httpx.AsyncClient) -> None:
        assert (await _post(client, b"{not json", _token())).json()["error"]["code"] == -32700
        batch = await _post(client, [_rpc("ping")], _token())
        assert batch.status_code == 400

    async def test_unknown_method(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("resources/list"), _token())
        assert resp.json()["error"]["code"] == -32601

    async def test_unsupported_protocol_version_header(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("ping"), _token(), **{"MCP-Protocol-Version": "1999-01-01"})
        assert resp.status_code == 400

    async def test_unknown_tool(self, client: httpx.AsyncClient) -> None:
        resp = await _post(client, _rpc("tools/call", {"name": "cogs_everything"}), _token())
        assert resp.json()["error"]["code"] == -32602


class TestInferenceUsageTool:
    async def test_returns_own_org_usage_matching_output_schema(
        self, client: httpx.AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        resp = await _post(client, _call(), _token())
        result = resp.json()["result"]
        assert result["isError"] is False
        data = result["structuredContent"]
        jsonschema.validate(data, TOOLS["inference_usage"].output_schema)
        assert data["org"] == "org-a"
        assert data["tokens"]["total"] == 1200
        assert data["list_price_estimate_usd"] == "0.012000"
        assert data["estimate"]["basis"] == "list_price_estimate"
        assert data["estimate"]["is_cash"] is False
        assert data["funding"]["status"] == "unattributed"
        assert "synthetic-quoting" not in json.dumps(data)
        assert json.loads(result["content"][0]["text"]) == data

    async def test_other_org_is_refused(
        self, client: httpx.AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        resp = await _post(client, _call(org="org-b"), _token())
        result = resp.json()["result"]
        assert result["isError"] is True
        assert result["content"][0]["text"].startswith("org_not_visible")
        assert "99999" not in resp.text

    async def test_token_for_org_b_sees_only_org_b(
        self, client: httpx.AsyncClient, db_session: AsyncSession
    ) -> None:
        await _seed(db_session)
        resp = await _post(client, _call(org="org-b"), _token(org_id="org-b"))
        data = resp.json()["result"]["structuredContent"]
        assert data["org"] == "org-b" and data["tokens"]["total"] == 99999

    @pytest.mark.parametrize(
        ("month", "code"),
        [
            ("2026-13", "invalid_arguments"),
            ("sept", "invalid_arguments"),
            ("2099-01", "month_in_future"),
        ],
    )
    async def test_month_validation(self, client: httpx.AsyncClient, month: str, code: str) -> None:
        result = (await _post(client, _call(month=month), _token())).json()["result"]
        assert result["isError"] is True
        assert result["content"][0]["text"].startswith(code)

    async def test_missing_and_extra_arguments(self, client: httpx.AsyncClient) -> None:
        body = _rpc(
            "tools/call", {"name": "inference_usage", "arguments": {"org": "org-a", "x": 1}}
        )
        text = (await _post(client, body, _token())).json()["result"]["content"][0]["text"]
        assert "month: required" in text and "x: unknown argument" in text

    async def test_empty_month_is_explicit(self, client: httpx.AsyncClient) -> None:
        data = (await _post(client, _call(), _token())).json()["result"]["structuredContent"]
        assert data["status"] == "empty"
        assert data["request_count"] is None
        assert data["tokens"]["total"] is None
        assert data["list_price_estimate_usd"] is None
        assert data["completeness"]["status"] == "empty"

    async def test_internal_error_is_contained(
        self, client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import nexus_api.mcp.tools as tools_mod

        async def boom(*_a: Any, **_k: Any) -> None:
            raise RuntimeError("org-a secret detail")

        monkeypatch.setattr(tools_mod, "build_inference_usage_report", boom)
        resp = await _post(client, _call(), _token())
        result = resp.json()["result"]
        assert result["isError"] is True
        assert "secret detail" not in resp.text


class TestAuditAndRateLimit:
    async def test_one_audit_line_without_arguments(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger="selva.mcp.audit")
        await _post(client, _call(org="org-a", month="2026-09"), _token())
        lines = [r.getMessage() for r in caplog.records if r.name == "selva.mcp.audit"]
        assert len(lines) == 1
        line = json.loads(lines[0].removeprefix("mcp.call "))
        assert set(line) == {"client", "tool", "outcome", "latency_ms", "args_sha256"}
        assert line["client"] == _CLIENT
        assert line["tool"] == "inference_usage"
        assert line["outcome"] == "ok"
        assert line["args_sha256"] == protocol.args_sha256({"org": "org-a", "month": "2026-09"})
        assert "org-a" not in lines[0] and "2026-09" not in lines[0]

    async def test_list_is_not_audited_as_a_call(
        self, client: httpx.AsyncClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.INFO, logger="selva.mcp.audit")
        await _post(client, _rpc("tools/list"), _token())
        assert not [r for r in caplog.records if r.name == "selva.mcp.audit"]

    async def test_rate_limit_per_client(
        self,
        client: httpx.AsyncClient,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        monkeypatch.setattr(get_settings(), "selva_mcp_rate_per_minute", 2)
        caplog.set_level(logging.INFO, logger="selva.mcp.audit")
        statuses = [(await _post(client, _rpc("ping"), _token())).status_code for _ in range(3)]
        assert statuses == [200, 200, 429]
        other = _token(sub="service-account:synthetic-fleet")
        assert (await _post(client, _rpc("ping"), other)).status_code == 200
        limited = [r.getMessage() for r in caplog.records if r.name == "selva.mcp.audit"]
        assert len(limited) == 1 and '"outcome": "rate_limited"' in limited[0]
