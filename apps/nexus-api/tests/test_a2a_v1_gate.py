"""Integration: the A2A v1.0.1 surface is feature-gated and additive.

Asserts the whole contract at the app-mount level:

- OFF by default: the v1 card + JSON-RPC endpoint are NOT mounted (404), and
  the legacy 0.7.0 surface is unaffected.
- ON (FEATURE_A2A_V1): the v1 card is served with the pinned version, ordered
  interfaces, no top-level id, and streaming reflecting the config; the
  JSON-RPC endpoint dispatches; the legacy surface KEEPS working (no regression).

These use ``create_app()`` with a custom Settings, mirroring
``test_a2a_public_url.py``. No database or Redis is required — the checks that
would touch them (task create/get/cancel round-trips) are covered at the router
level in ``packages/a2a/tests/test_a2a_v1.py`` with stub adapters.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus_api.config import Settings


def _app(monkeypatch: pytest.MonkeyPatch, **overrides):
    import nexus_api.main as main_mod

    settings = Settings(
        database_url="sqlite+aiosqlite://",
        environment="development",
        public_app_url="https://app.selva.town",
        **overrides,
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: settings)
    return main_mod.create_app()


class TestGateOff:
    def test_v1_default_is_off_in_settings(self) -> None:
        s = Settings(database_url="sqlite+aiosqlite://", environment="development")
        assert s.feature_a2a_v1 is False
        assert s.a2a_v1_streaming is False

    def test_v1_card_not_mounted_when_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(_app(monkeypatch))  # gate defaults off
        resp = client.get("/api/v1/a2a/v1/.well-known/agent-card.json")
        assert resp.status_code == 404

    def test_v1_jsonrpc_not_mounted_when_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(_app(monkeypatch))
        resp = client.post(
            "/api/v1/a2a/v1/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "x"}},
        )
        assert resp.status_code == 404

    def test_legacy_surface_unaffected_when_v1_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Zero behaviour change: the legacy 0.7.0 card still serves.
        client = TestClient(_app(monkeypatch))
        resp = client.get("/api/v1/a2a/.well-known/agent.json")
        assert resp.status_code == 200
        assert resp.json()["version"] == "0.7.0"
        assert resp.json()["url"] == "https://app.selva.town"


class TestGateOn:
    def test_v1_card_served_when_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(_app(monkeypatch, feature_a2a_v1=True))
        resp = client.get("/api/v1/a2a/v1/.well-known/agent-card.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["protocolVersion"] == "/v1.0.1/"
        assert "id" not in card
        assert card["capabilities"]["streaming"] is False  # a2a_v1_streaming default off

    def test_v1_card_interface_points_at_versioned_endpoint(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = TestClient(_app(monkeypatch, feature_a2a_v1=True))
        card = client.get("/api/v1/a2a/v1/.well-known/agent-card.json").json()
        ifaces = card["supportedInterfaces"]
        assert ifaces[0]["protocolBinding"] == "JSONRPC"
        assert ifaces[0]["url"] == "https://app.selva.town/api/v1/a2a/v1/"

    def test_streaming_capability_follows_setting(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = TestClient(_app(monkeypatch, feature_a2a_v1=True, a2a_v1_streaming=True))
        card = client.get("/api/v1/a2a/v1/.well-known/agent-card.json").json()
        assert card["capabilities"]["streaming"] is True

    def test_v1_jsonrpc_dispatches_when_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A malformed request reaches the router (not a 404) and returns a
        # JSON-RPC error — proof the endpoint is mounted and dispatching.
        client = TestClient(_app(monkeypatch, feature_a2a_v1=True))
        resp = client.post(
            "/api/v1/a2a/v1/",
            json={"id": 1, "method": "tasks/get", "params": {"id": "x"}},  # no jsonrpc:2.0
        )
        assert resp.status_code == 200
        assert resp.json()["error"]["code"] == -32600

    def test_streaming_method_rejected_when_streaming_off(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = TestClient(_app(monkeypatch, feature_a2a_v1=True, a2a_v1_streaming=False))
        resp = client.post(
            "/api/v1/a2a/v1/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/stream",
                "params": {"message": {"parts": [{"text": "x"}]}},
            },
        )
        assert resp.json()["error"]["code"] == -32601

    def test_legacy_surface_still_served_when_v1_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Both surfaces coexist: legacy card AND v1 card both serve.
        client = TestClient(_app(monkeypatch, feature_a2a_v1=True))
        legacy = client.get("/api/v1/a2a/.well-known/agent.json")
        v1 = client.get("/api/v1/a2a/v1/.well-known/agent-card.json")
        assert legacy.status_code == 200
        assert legacy.json()["version"] == "0.7.0"
        assert v1.status_code == 200
        assert v1.json()["version"] == "1.0.1"
