"""A2A task routes need a verified caller and the intake switch; the card stays public."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexus_api.config import Settings


def _client(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> TestClient:
    import nexus_api.auth as auth_mod
    import nexus_api.main as main_mod

    custom = Settings(
        database_url="sqlite+aiosqlite://",
        environment="development",
        dev_auth_bypass=True,
        a2a_inbound_enabled=enabled,
        _env_file=None,  # type: ignore[call-arg]
    )
    monkeypatch.setattr(main_mod, "get_settings", lambda: custom)
    app = main_mod.create_app()
    app.dependency_overrides[auth_mod.get_settings] = lambda: custom
    return TestClient(app)


def test_intake_is_off_by_default() -> None:
    settings = Settings(environment="development", _env_file=None)  # type: ignore[call-arg]
    assert settings.a2a_inbound_enabled is False


def test_agent_card_stays_public(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, enabled=False)
    resp = client.get("/api/v1/a2a/.well-known/agent.json")
    assert resp.status_code == 200
    assert resp.json()["authentication"] == {"schemes": ["bearer"]}


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/v1/a2a/tasks/send"),
        ("post", "/api/v1/a2a/tasks/sendSubscribe"),
        ("get", "/api/v1/a2a/tasks/00000000-0000-0000-0000-000000000000"),
    ],
)
def test_task_routes_reject_callers_without_a_token(
    monkeypatch: pytest.MonkeyPatch, method: str, path: str
) -> None:
    client = _client(monkeypatch, enabled=True)
    kwargs = {"json": {"description": "x"}} if method == "post" else {}
    resp = getattr(client, method)(path, **kwargs)
    assert resp.status_code in (401, 403)


def test_task_routes_refuse_verified_callers_while_intake_is_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch, enabled=False)
    resp = client.post(
        "/api/v1/a2a/tasks/send",
        json={"description": "x"},
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 503
    assert resp.json()["detail"] == "A2A task intake is not enabled"


def test_verified_callers_pass_the_gate_when_intake_is_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch, enabled=True)
    resp = client.get(
        "/api/v1/a2a/tasks/not-a-uuid",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    assert resp.json()["error"] == "Invalid task ID"
