"""Tests for the machine-edge credentials in ``service_auth``.

Janua and the services are faked with ``httpx.MockTransport``: every request a
tool or the token provider sends is recorded, and nothing leaves the process.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Iterator
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from selva_tools.builtins import phygital_tools, service_auth
from selva_tools.builtins.operations import InventoryCheckTool
from selva_tools.builtins.phygital_tools import (
    GenerateParametricModelTool,
    GetProductionOrderStatusTool,
)
from selva_tools.builtins.service_auth import (
    PRAVARA_EDGE,
    YANTRA4D_EDGE,
    ClientCredentialsTokenProvider,
    TokenMintError,
)

ISSUER = "https://auth.test"
TOKEN_URL = f"{ISSUER}/api/v1/oauth/token"
YANTRA_URL = "https://yantra.test"
PRAVARA_URL = "https://pravara.test"
ORDER_ID = "7b0c6c2e-3f5d-4a8e-9c1b-2d4e6f8a0b1c"

YANTRA_ID = "jnc_yantra_fixture"
YANTRA_SECRET = "yantra-fixture-secret"
PRAVARA_ID = "jnc_pravara_fixture"
PRAVARA_SECRET = "pravara-fixture-secret"


def _token_ok(token: str, expires_in: Any = 3600) -> httpx.Response:
    body: dict[str, Any] = {"access_token": token, "token_type": "Bearer"}
    if expires_in is not None:
        body["expires_in"] = expires_in
    return httpx.Response(200, json=body)


def _jwt(claims: dict[str, Any]) -> str:
    """An unsigned JWT; the provider reads ``exp`` from it only to time its cache."""

    def part(value: dict[str, Any]) -> str:
        raw = json.dumps(value).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(claims)}.c2lnbmF0dXJl"


def _basic(client_id: str, client_secret: str) -> str:
    return "Basic " + base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()


class _FakeNetwork:
    """Janua's token endpoint plus the Yantra4D and Pravara-MES routes."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        #: Responses (or exceptions) for successive token requests; when it
        #: runs out, each request gets a fresh ``minted-<n>`` token.
        self.token_replies: list[httpx.Response | Exception] = []
        self.minted = 0

    def token_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url) == TOKEN_URL]

    def service_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if str(r.url) != TOKEN_URL]

    async def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if str(request.url) == TOKEN_URL:
            # Yield so that concurrent callers reach the provider's lock.
            await asyncio.sleep(0.01)
            if self.token_replies:
                reply = self.token_replies.pop(0)
                if isinstance(reply, Exception):
                    raise reply
                return reply
            self.minted += 1
            return _token_ok(f"minted-{self.minted}")
        if request.url.path == "/api/render":
            return httpx.Response(200, json={"status": "success", "parts": []})
        if request.url.path.startswith("/v1/orders/"):
            return httpx.Response(200, json={"id": ORDER_ID, "status": "queued"})
        if request.url.path == "/v1/inventory":
            return httpx.Response(200, json={"data": [{"sku": "SKU-1", "quantity_available": 2}]})
        return httpx.Response(404, json={"error": "not found"})


@pytest.fixture
def network(monkeypatch: pytest.MonkeyPatch) -> Iterator[_FakeNetwork]:
    fake = _FakeNetwork()
    real_async_client = httpx.AsyncClient

    class _MockedAsyncClient(real_async_client):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            kwargs["transport"] = httpx.MockTransport(fake.handle)
            super().__init__(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", _MockedAsyncClient)
    yield fake


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for edge in (YANTRA4D_EDGE, PRAVARA_EDGE):
        monkeypatch.delenv(edge.client_id_env, raising=False)
        monkeypatch.delenv(edge.client_secret_env, raising=False)
        for name in edge.token_env:
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("JANUA_ISSUER_URL", ISSUER)
    monkeypatch.setenv("PRAVARA_MES_API_URL", PRAVARA_URL)
    monkeypatch.setattr(phygital_tools, "YANTRA4D_API_URL", YANTRA_URL)
    monkeypatch.setattr(phygital_tools, "PRAVARA_MES_API_URL", PRAVARA_URL)
    monkeypatch.setattr(phygital_tools, "YANTRA4D_API_TOKEN", "")
    monkeypatch.setattr(phygital_tools, "PRAVARA_MES_API_TOKEN", "")
    service_auth.reset_token_cache()
    yield
    service_auth.reset_token_cache()


def _configure_yantra(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(YANTRA4D_EDGE.client_id_env, YANTRA_ID)
    monkeypatch.setenv(YANTRA4D_EDGE.client_secret_env, YANTRA_SECRET)


def _configure_pravara(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PRAVARA_EDGE.client_id_env, PRAVARA_ID)
    monkeypatch.setenv(PRAVARA_EDGE.client_secret_env, PRAVARA_SECRET)


async def _render() -> Any:
    return await GenerateParametricModelTool().execute(project_slug="demo")


class TestMinting:
    @pytest.mark.asyncio
    async def test_mints_with_client_credentials_and_sends_the_token(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)

        result = await _render()

        assert result.success, result.error
        [mint] = network.token_requests()
        assert mint.method == "POST"
        assert mint.headers["Authorization"] == _basic(YANTRA_ID, YANTRA_SECRET)
        assert mint.headers["Content-Type"] == "application/x-www-form-urlencoded"
        assert parse_qs(mint.content.decode()) == {
            "grant_type": ["client_credentials"],
            "scope": ["yantra4d:render"],
        }
        [render] = network.service_requests()
        assert str(render.url) == f"{YANTRA_URL}/api/render"
        assert render.headers["Authorization"] == "Bearer minted-1"
        assert render.headers["X-Service-Actor"] == "selva-agent"

    @pytest.mark.asyncio
    async def test_pravara_edge_requests_the_read_scope(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_pravara(monkeypatch)

        order = await GetProductionOrderStatusTool().execute(order_id=ORDER_ID)
        inventory = await InventoryCheckTool().execute(sku="SKU-1")

        assert order.success, order.error
        assert inventory.success, inventory.error
        [mint] = network.token_requests()
        assert mint.headers["Authorization"] == _basic(PRAVARA_ID, PRAVARA_SECRET)
        assert parse_qs(mint.content.decode())["scope"] == ["pravara-mes:read"]
        assert [r.headers["Authorization"] for r in network.service_requests()] == [
            "Bearer minted-1",
            "Bearer minted-1",
        ]

    @pytest.mark.asyncio
    async def test_each_edge_holds_its_own_token(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)
        _configure_pravara(monkeypatch)

        await _render()
        await GetProductionOrderStatusTool().execute(order_id=ORDER_ID)

        scopes = [parse_qs(r.content.decode())["scope"] for r in network.token_requests()]
        assert scopes == [["yantra4d:render"], ["pravara-mes:read"]]
        render, order = network.service_requests()
        assert render.headers["Authorization"] == "Bearer minted-1"
        assert order.headers["Authorization"] == "Bearer minted-2"

    @pytest.mark.asyncio
    async def test_client_credentials_win_over_a_static_token(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)
        monkeypatch.setattr(phygital_tools, "YANTRA4D_API_TOKEN", "static-yantra")

        await _render()

        [render] = network.service_requests()
        assert render.headers["Authorization"] == "Bearer minted-1"


class TestCaching:
    @pytest.mark.asyncio
    async def test_reuses_the_token_across_calls(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)

        for _ in range(3):
            assert (await _render()).success

        assert len(network.token_requests()) == 1
        assert {r.headers["Authorization"] for r in network.service_requests()} == {
            "Bearer minted-1"
        }

    @pytest.mark.asyncio
    async def test_concurrent_calls_share_one_mint(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)

        results = await asyncio.gather(*(_render() for _ in range(5)))

        assert all(result.success for result in results)
        assert len(network.token_requests()) == 1
        assert len(network.service_requests()) == 5

    @pytest.mark.asyncio
    async def test_refreshes_sixty_seconds_before_expires_in(self, network: _FakeNetwork) -> None:
        now = [1000.0]
        network.token_replies = [_token_ok("first", expires_in=120), _token_ok("second")]
        provider = ClientCredentialsTokenProvider(
            token_url=TOKEN_URL,
            client_id=YANTRA_ID,
            client_secret=YANTRA_SECRET,
            scope="yantra4d:render",
            clock=lambda: now[0],
        )

        assert await provider.get_token() == "first"
        now[0] += 59.9
        assert await provider.get_token() == "first"
        now[0] += 0.1
        assert await provider.get_token() == "second"
        assert len(network.token_requests()) == 2

    @pytest.mark.asyncio
    async def test_a_sooner_exp_claim_bounds_the_cache(self, network: _FakeNetwork) -> None:
        wall_now = 1_800_000_000.0
        now = [0.0]
        token = _jwt({"sub": "service-account:jnc_x", "exp": int(wall_now) + 100})
        network.token_replies = [_token_ok(token, expires_in=3600), _token_ok("next")]
        provider = ClientCredentialsTokenProvider(
            token_url=TOKEN_URL,
            client_id=YANTRA_ID,
            client_secret=YANTRA_SECRET,
            scope="yantra4d:render",
            clock=lambda: now[0],
            wall_clock=lambda: wall_now,
        )

        assert await provider.get_token() == token
        now[0] = 39.0
        assert await provider.get_token() == token
        now[0] = 40.0
        assert await provider.get_token() == "next"

    @pytest.mark.asyncio
    async def test_exp_claim_alone_sets_the_lifetime(self, network: _FakeNetwork) -> None:
        wall_now = 1_800_000_000.0
        now = [0.0]
        token = _jwt({"exp": int(wall_now) + 600})
        network.token_replies = [_token_ok(token, expires_in=None), _token_ok("next")]
        provider = ClientCredentialsTokenProvider(
            token_url=TOKEN_URL,
            client_id=YANTRA_ID,
            client_secret=YANTRA_SECRET,
            scope="yantra4d:render",
            clock=lambda: now[0],
            wall_clock=lambda: wall_now,
        )

        assert await provider.get_token() == token
        now[0] = 539.0
        assert await provider.get_token() == token
        now[0] = 540.0
        assert await provider.get_token() == "next"

    @pytest.mark.asyncio
    async def test_a_token_without_a_lifetime_is_not_cached(self, network: _FakeNetwork) -> None:
        network.token_replies = [_token_ok("opaque-1", None), _token_ok("opaque-2", None)]
        provider = ClientCredentialsTokenProvider(
            token_url=TOKEN_URL,
            client_id=YANTRA_ID,
            client_secret=YANTRA_SECRET,
            scope="yantra4d:render",
        )

        assert await provider.get_token() == "opaque-1"
        assert await provider.get_token() == "opaque-2"

    @pytest.mark.asyncio
    async def test_changed_credentials_mint_again(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)
        await _render()
        monkeypatch.setenv(YANTRA4D_EDGE.client_secret_env, "rotated-fixture-secret")

        await _render()

        first, second = network.token_requests()
        assert first.headers["Authorization"] == _basic(YANTRA_ID, YANTRA_SECRET)
        assert second.headers["Authorization"] == _basic(YANTRA_ID, "rotated-fixture-secret")


class TestMintFailure:
    @pytest.mark.asyncio
    async def test_rejected_credentials_fail_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        network: _FakeNetwork,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _configure_yantra(monkeypatch)
        network.token_replies = [
            httpx.Response(401, json={"detail": "invalid_client: Invalid client_secret"})
        ]

        with caplog.at_level(logging.DEBUG):
            result = await _render()

        assert not result.success
        assert result.error == (
            "Yantra4D machine token unavailable: Janua token endpoint answered HTTP 401 "
            "(invalid_client); no request was sent."
        )
        assert network.service_requests() == []
        assert YANTRA_SECRET not in caplog.text
        assert "Janua machine token not issued for Yantra4D" in caplog.text

    @pytest.mark.asyncio
    async def test_a_failed_mint_is_retried_on_the_next_call(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)
        network.token_replies = [httpx.Response(503, text="upstream unavailable")]

        first = await _render()
        second = await _render()

        assert not first.success
        assert "HTTP 503" in (first.error or "")
        assert second.success, second.error
        assert len(network.token_requests()) == 2
        [render] = network.service_requests()
        assert render.headers["Authorization"] == "Bearer minted-1"

    @pytest.mark.asyncio
    async def test_unreachable_token_endpoint(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        _configure_yantra(monkeypatch)
        network.token_replies = [httpx.ConnectError("connection refused")]

        result = await _render()

        assert not result.success
        assert "Janua token endpoint unreachable (ConnectError)" in (result.error or "")
        assert network.service_requests() == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("reply", "reason"),
        [
            (httpx.Response(200, json={"token_type": "Bearer"}), "carried no access_token"),
            (httpx.Response(200, json={"access_token": ""}), "carried no access_token"),
            (httpx.Response(200, json=["not", "an", "object"]), "carried no access_token"),
            (httpx.Response(200, text="<html>login</html>"), "is not JSON"),
        ],
    )
    async def test_unusable_token_responses(
        self,
        monkeypatch: pytest.MonkeyPatch,
        network: _FakeNetwork,
        reply: httpx.Response,
        reason: str,
    ) -> None:
        _configure_yantra(monkeypatch)
        network.token_replies = [reply]

        result = await _render()

        assert not result.success
        assert reason in (result.error or "")
        assert network.service_requests() == []

    @pytest.mark.asyncio
    async def test_provider_raises_mint_errors(self, network: _FakeNetwork) -> None:
        network.token_replies = [httpx.Response(400, json={"error": "invalid_scope"})]
        provider = ClientCredentialsTokenProvider(
            token_url=TOKEN_URL,
            client_id=YANTRA_ID,
            client_secret=YANTRA_SECRET,
            scope="yantra4d:render",
        )

        with pytest.raises(TokenMintError, match=r"HTTP 400 \(invalid_scope\)"):
            await provider.get_token()


class TestStaticFallback:
    @pytest.mark.asyncio
    async def test_static_token_without_client_credentials(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork
    ) -> None:
        monkeypatch.setattr(phygital_tools, "YANTRA4D_API_TOKEN", "static-yantra")
        monkeypatch.setenv("SELVA_PRAVARA_SERVICE_TOKEN", "static-pravara")

        render = await _render()
        inventory = await InventoryCheckTool().execute(sku="SKU-1")

        assert render.success, render.error
        assert inventory.success, inventory.error
        assert network.token_requests() == []
        assert [r.headers["Authorization"] for r in network.service_requests()] == [
            "Bearer static-yantra",
            "Bearer static-pravara",
        ]

    @pytest.mark.asyncio
    async def test_nothing_configured_sends_nothing(self, network: _FakeNetwork) -> None:
        result = await _render()

        assert not result.success
        assert result.error == (
            "Yantra4D service token not configured (set SELVA_YANTRA4D_CLIENT_ID and "
            "SELVA_YANTRA4D_CLIENT_SECRET, or YANTRA4D_API_TOKEN or "
            "SELVA_YANTRA4D_SERVICE_TOKEN or SELVA_SERVICE_TOKEN); no request was sent."
        )
        assert network.requests == []


class TestConfiguration:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("present", ["id", "secret"])
    async def test_half_a_client_pair_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch, network: _FakeNetwork, present: str
    ) -> None:
        if present == "id":
            monkeypatch.setenv(YANTRA4D_EDGE.client_id_env, YANTRA_ID)
            absent = YANTRA4D_EDGE.client_secret_env
        else:
            monkeypatch.setenv(YANTRA4D_EDGE.client_secret_env, YANTRA_SECRET)
            absent = YANTRA4D_EDGE.client_id_env
        monkeypatch.setattr(phygital_tools, "YANTRA4D_API_TOKEN", "static-yantra")

        result = await _render()

        assert not result.success
        assert f"{absent} is not set" in (result.error or "")
        assert network.requests == []

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("issuer", "reason"),
        [
            ("", "JANUA_ISSUER_URL is not set"),
            ("http://auth.example.com", "JANUA_ISSUER_URL must be an https URL"),
            ("auth.example.com", "JANUA_ISSUER_URL must be an https URL"),
        ],
    )
    async def test_unusable_issuer_fails_closed(
        self,
        monkeypatch: pytest.MonkeyPatch,
        network: _FakeNetwork,
        issuer: str,
        reason: str,
    ) -> None:
        _configure_yantra(monkeypatch)
        monkeypatch.setenv("JANUA_ISSUER_URL", issuer)

        result = await _render()

        assert not result.success
        assert reason in (result.error or "")
        assert network.requests == []

    @pytest.mark.parametrize(
        ("issuer", "url"),
        [
            ("https://auth.madfam.io", "https://auth.madfam.io/api/v1/oauth/token"),
            ("https://auth.madfam.io/", "https://auth.madfam.io/api/v1/oauth/token"),
            ("http://localhost:8001", "http://localhost:8001/api/v1/oauth/token"),
        ],
    )
    def test_token_url_comes_from_the_issuer(
        self, monkeypatch: pytest.MonkeyPatch, issuer: str, url: str
    ) -> None:
        monkeypatch.setenv("JANUA_ISSUER_URL", issuer)

        assert service_auth.janua_token_url() == (url, "")


class TestNoCredentialLeaks:
    @pytest.mark.asyncio
    async def test_logs_carry_no_secret_and_no_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
        network: _FakeNetwork,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        _configure_yantra(monkeypatch)
        network.token_replies = [_token_ok("token-value-that-must-stay-private")]

        with caplog.at_level(logging.DEBUG):
            result = await _render()

        assert result.success, result.error
        assert "token-value-that-must-stay-private" not in caplog.text
        assert YANTRA_SECRET not in caplog.text
        assert "token-value-that-must-stay-private" not in repr(result)

    def test_provider_repr_hides_the_secret(self) -> None:
        provider = ClientCredentialsTokenProvider(
            token_url=TOKEN_URL,
            client_id=YANTRA_ID,
            client_secret=YANTRA_SECRET,
            scope="yantra4d:render",
        )

        assert YANTRA_SECRET not in repr(provider)
        assert "yantra4d:render" in repr(provider)
