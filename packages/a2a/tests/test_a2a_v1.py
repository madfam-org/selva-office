"""Tests for the Selva A2A v1.0.1-compatible surface and task announcer.

These exercise the additive v1 layer only; the legacy 0.7.0 surface is covered
by ``test_a2a.py`` and is never touched here. The announcer tests use a real
local ASGI intake server (no mocks of our own code).
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from selva_a2a.announce import (
    ENV_INTAKE_TOKEN,
    ENV_INTAKE_URL,
    announce_task,
    build_announcement,
    is_announcer_enabled,
)
from selva_a2a.v1 import (
    A2A_V1_PROTOCOL_VERSION,
    AgentCapabilities,
    AgentCardV1,
    AgentInterface,
    MessageSendParams,
    TaskState,
    create_a2a_v1_router,
    selva_status_to_task_state,
)

# -- Task-state constants -----------------------------------------------------


class TestTaskState:
    def test_all_nine_states_present_screaming_snake(self):
        # The v1 surface must advertise the complete ProtoJSON enum, all nine,
        # in SCREAMING_SNAKE_CASE.
        expected = {
            "TASK_STATE_UNSPECIFIED",
            "TASK_STATE_SUBMITTED",
            "TASK_STATE_WORKING",
            "TASK_STATE_COMPLETED",
            "TASK_STATE_FAILED",
            "TASK_STATE_CANCELED",
            "TASK_STATE_REJECTED",
            "TASK_STATE_INPUT_REQUIRED",
            "TASK_STATE_AUTH_REQUIRED",
        }
        assert {s.value for s in TaskState} == expected
        assert len(list(TaskState)) == 9

    def test_no_v03_kebab_case_spellings(self):
        # v0.3 kebab-case spellings must NEVER appear on the v1 surface.
        for s in TaskState:
            assert "-" not in s.value
            assert s.value == s.value.upper()

    def test_input_required_distinct_from_auth_required(self):
        # The two interrupted states must be distinct — the observer renders a
        # credential request differently from a content question.
        assert TaskState.INPUT_REQUIRED != TaskState.AUTH_REQUIRED
        assert TaskState.INPUT_REQUIRED.value == "TASK_STATE_INPUT_REQUIRED"
        assert TaskState.AUTH_REQUIRED.value == "TASK_STATE_AUTH_REQUIRED"


class TestStatusMapping:
    """Honest mapping of Selva's real persisted statuses -> v1 states."""

    @pytest.mark.parametrize(
        ("selva_status", "expected"),
        [
            ("pending", TaskState.SUBMITTED),
            ("queued", TaskState.SUBMITTED),
            ("running", TaskState.WORKING),
            ("completed", TaskState.COMPLETED),
            ("failed", TaskState.FAILED),
            ("cancelled", TaskState.CANCELED),
            ("canceled", TaskState.CANCELED),  # US spelling tolerated
            ("RUNNING", TaskState.WORKING),  # case-insensitive
        ],
    )
    def test_reachable_statuses_map(self, selva_status, expected):
        assert selva_status_to_task_state(selva_status) == expected

    @pytest.mark.parametrize("unknown", [None, "", "waiting_approval", "blocked", "bogus"])
    def test_unreachable_or_unknown_fall_back_to_unspecified(self, unknown):
        # Selva has no persisted INPUT_REQUIRED/AUTH_REQUIRED/REJECTED status,
        # so those never appear; unknown statuses do NOT get coerced into an
        # interrupted state — they fall back to UNSPECIFIED.
        assert selva_status_to_task_state(unknown) == TaskState.UNSPECIFIED

    def test_no_interrupted_state_is_ever_produced_by_the_mapping(self):
        # Belt-and-suspenders: the mapping never yields an interrupted state.
        never = {TaskState.INPUT_REQUIRED, TaskState.AUTH_REQUIRED, TaskState.REJECTED}
        for candidate in [
            None,
            "pending",
            "queued",
            "running",
            "completed",
            "failed",
            "cancelled",
            "waiting_approval",
            "approved",
            "denied",
            "timeout",
            "blocked",
        ]:
            assert selva_status_to_task_state(candidate) not in never


# -- Card + router fixtures ---------------------------------------------------


def _build_app(*, streaming: bool = False, configured: bool = True) -> FastAPI:
    """A minimal FastAPI app with the v1 router mounted for tests."""

    async def create_task(params: MessageSendParams) -> str:
        # Echo the tenant into the id so tests can assert threading.
        return "task-001"

    async def get_task(task_id: str):
        if task_id == "task-001":
            return (TaskState.WORKING, "in progress")
        if task_id == "task-done":
            return (TaskState.COMPLETED, None)
        return None

    async def cancel_task(task_id: str):
        if task_id == "task-001":
            return (TaskState.CANCELED, None)
        if task_id == "task-done":
            # Already terminal — returned unchanged (no-op).
            return (TaskState.COMPLETED, None)
        return None

    def get_card() -> AgentCardV1:
        return AgentCardV1(
            supported_interfaces=[
                AgentInterface(
                    url="https://selva.example/api/v1/a2a/v1/", protocol_binding="JSONRPC"
                ),
                AgentInterface(url="https://selva.example/grpc", protocol_binding="GRPC"),
            ],
            capabilities=AgentCapabilities(streaming=streaming),
        )

    app = FastAPI()
    router = create_a2a_v1_router(
        prefix="/a2a/v1",
        get_card=get_card,
        create_task=create_task if configured else None,
        get_task=get_task if configured else None,
        cancel_task=cancel_task if configured else None,
        streaming=streaming,
        stream_poll_interval_seconds=0.01,
        stream_max_polls=5,
    )
    app.include_router(router, prefix="/api/v1")
    return app


class TestAgentCardV1:
    def test_pinned_version_and_shape(self):
        client = TestClient(_build_app())
        resp = client.get("/api/v1/a2a/v1/.well-known/agent-card.json")
        assert resp.status_code == 200
        card = resp.json()
        assert card["protocolVersion"] == A2A_V1_PROTOCOL_VERSION == "/v1.0.1/"
        # v1.0 card shape: no top-level id.
        assert "id" not in card
        assert card["version"] == "1.0.1"

    def test_ordered_supported_interfaces_and_open_binding(self):
        client = TestClient(_build_app())
        card = client.get("/api/v1/a2a/v1/.well-known/agent-card.json").json()
        ifaces = card["supportedInterfaces"]
        # Order preserved; protocolBinding is an open string.
        assert [i["protocolBinding"] for i in ifaces] == ["JSONRPC", "GRPC"]
        assert ifaces[0]["url"].endswith("/api/v1/a2a/v1/")

    def test_capabilities_streaming_reflects_router(self):
        assert (
            TestClient(_build_app(streaming=False))
            .get("/api/v1/a2a/v1/.well-known/agent-card.json")
            .json()["capabilities"]["streaming"]
            is False
        )
        assert (
            TestClient(_build_app(streaming=True))
            .get("/api/v1/a2a/v1/.well-known/agent-card.json")
            .json()["capabilities"]["streaming"]
            is True
        )

    def test_legacy_well_known_path_not_served_by_v1_router(self):
        # The v1 router serves ONLY agent-card.json, never the legacy agent.json.
        client = TestClient(_build_app())
        assert client.get("/api/v1/a2a/v1/.well-known/agent.json").status_code == 404


class TestJsonRpcHappyPaths:
    def _rpc(self, client, method, params, req_id=1):
        return client.post(
            "/api/v1/a2a/v1/",
            json={"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
        ).json()

    def test_message_send_returns_submitted_snapshot(self):
        client = TestClient(_build_app())
        r = self._rpc(
            client,
            "message/send",
            {"message": {"role": "ROLE_USER", "parts": [{"text": "hello"}]}},
        )
        assert r["jsonrpc"] == "2.0"
        assert r["result"]["id"] == "task-001"
        assert r["result"]["status"]["state"] == "TASK_STATE_SUBMITTED"

    def test_message_send_accepts_data_and_file_parts(self):
        client = TestClient(_build_app())
        r = self._rpc(
            client,
            "message/send",
            {
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "t"}, {"data": {"k": 1}}, {"file": {"uri": "x"}}],
                }
            },
        )
        assert "result" in r

    def test_tenant_echoed_back(self):
        client = TestClient(_build_app())
        r = self._rpc(
            client,
            "message/send",
            {"message": {"parts": [{"text": "hi"}]}, "tenant": "acme-corp"},
        )
        assert r["result"]["tenant"] == "acme-corp"

    def test_tenant_absent_not_echoed(self):
        client = TestClient(_build_app())
        r = self._rpc(client, "message/send", {"message": {"parts": [{"text": "hi"}]}})
        assert "tenant" not in r["result"]

    def test_tasks_get_returns_state_and_update(self):
        client = TestClient(_build_app())
        r = self._rpc(client, "tasks/get", {"id": "task-001"})
        assert r["result"]["id"] == "task-001"
        assert r["result"]["status"]["state"] == "TASK_STATE_WORKING"
        assert r["result"]["status"]["update"] == "in progress"

    def test_tasks_cancel_returns_canceled(self):
        client = TestClient(_build_app())
        r = self._rpc(client, "tasks/cancel", {"id": "task-001"})
        assert r["result"]["status"]["state"] == "TASK_STATE_CANCELED"

    def test_tasks_cancel_on_terminal_is_noop_snapshot(self):
        # GROUNDED: duplicate terminal snapshots tolerated as no-op.
        client = TestClient(_build_app())
        r = self._rpc(client, "tasks/cancel", {"id": "task-done"})
        assert r["result"]["status"]["state"] == "TASK_STATE_COMPLETED"

    def test_tasks_get_echoes_tenant_when_supplied(self):
        client = TestClient(_build_app())
        r = self._rpc(client, "tasks/get", {"id": "task-001", "tenant": "t1"})
        assert r["result"]["tenant"] == "t1"


class TestJsonRpcErrors:
    def _post(self, client, body):
        return client.post("/api/v1/a2a/v1/", json=body).json()

    def test_not_jsonrpc_2_0_is_invalid_request(self):
        client = TestClient(_build_app())
        r = self._post(client, {"id": 1, "method": "tasks/get", "params": {"id": "x"}})
        assert r["error"]["code"] == -32600

    def test_missing_method_is_invalid_request(self):
        client = TestClient(_build_app())
        r = self._post(client, {"jsonrpc": "2.0", "id": 1, "params": {}})
        assert r["error"]["code"] == -32600

    def test_unknown_method_is_method_not_found(self):
        client = TestClient(_build_app())
        r = self._post(
            client, {"jsonrpc": "2.0", "id": 1, "method": "does/not/exist", "params": {}}
        )
        assert r["error"]["code"] == -32601

    def test_params_not_object_is_invalid_params(self):
        client = TestClient(_build_app())
        r = self._post(
            client, {"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": ["not", "obj"]}
        )
        assert r["error"]["code"] == -32602

    def test_message_send_missing_parts_is_invalid_params(self):
        client = TestClient(_build_app())
        r = self._post(
            client,
            {"jsonrpc": "2.0", "id": 1, "method": "message/send", "params": {"message": {}}},
        )
        assert r["error"]["code"] == -32602

    def test_message_send_bad_part_is_invalid_params(self):
        client = TestClient(_build_app())
        r = self._post(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"parts": [{"nonsense": 1}]}},
            },
        )
        assert r["error"]["code"] == -32602

    def test_tasks_get_missing_id_is_invalid_params(self):
        client = TestClient(_build_app())
        r = self._post(client, {"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {}})
        assert r["error"]["code"] == -32602

    def test_tasks_get_not_found_is_error(self):
        client = TestClient(_build_app())
        r = self._post(
            client, {"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "ghost"}}
        )
        assert r["error"]["code"] == -32602
        assert "not found" in r["error"]["message"]

    def test_malformed_json_body_is_parse_error(self):
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/a2a/v1/",
            content=b"{not json",
            headers={"content-type": "application/json"},
        )
        assert resp.json()["error"]["code"] == -32700


class TestStreaming:
    def test_message_stream_disabled_returns_method_not_found(self):
        client = TestClient(_build_app(streaming=False))
        r = client.post(
            "/api/v1/a2a/v1/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/stream",
                "params": {"message": {"parts": [{"text": "go"}]}},
            },
        ).json()
        assert r["error"]["code"] == -32601

    def test_message_stream_enabled_emits_sse_snapshots(self):
        client = TestClient(_build_app(streaming=True))
        with client.stream(
            "POST",
            "/api/v1/a2a/v1/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/stream",
                "params": {"message": {"parts": [{"text": "go"}]}, "tenant": "t9"},
            },
        ) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            body = "".join(resp.iter_text())
        # First snapshot is SUBMITTED; the get_task stub returns WORKING for
        # task-001, which is non-terminal, so the stream stops at the poll bound.
        assert "TASK_STATE_SUBMITTED" in body
        assert "TASK_STATE_WORKING" in body
        assert "t9" in body  # tenant threaded through the stream


class TestUnconfiguredAdapters:
    def test_send_without_creator_is_internal_error(self):
        client = TestClient(_build_app(configured=False))
        r = client.post(
            "/api/v1/a2a/v1/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {"message": {"parts": [{"text": "x"}]}},
            },
        ).json()
        assert r["error"]["code"] == -32603

    def test_get_without_getter_is_internal_error(self):
        client = TestClient(_build_app(configured=False))
        r = client.post(
            "/api/v1/a2a/v1/",
            json={"jsonrpc": "2.0", "id": 1, "method": "tasks/get", "params": {"id": "x"}},
        ).json()
        assert r["error"]["code"] == -32603


# -- Announcer ----------------------------------------------------------------


def _intake_app(received: list[dict], *, status_code: int = 200, require_token: str | None = None):
    """A real local ASGI intake server that records announcement bodies."""
    app = FastAPI()

    @app.post("/intake")
    async def intake(request: Request) -> JSONResponse:
        if require_token is not None:
            auth = request.headers.get("authorization", "")
            if auth != f"Bearer {require_token}":
                return JSONResponse({"error": "unauthorized"}, status_code=401)
        received.append(await request.json())
        return JSONResponse({"ok": True}, status_code=status_code)

    return app


def _client_for(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://intake.local")


class TestAnnouncerConfig:
    def test_off_when_env_absent(self, monkeypatch):
        monkeypatch.delenv(ENV_INTAKE_URL, raising=False)
        assert is_announcer_enabled() is False

    def test_off_when_env_blank(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "   ")
        assert is_announcer_enabled() is False

    def test_off_when_env_invalid_scheme(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "ftp://nope")
        assert is_announcer_enabled() is False

    def test_on_when_env_valid(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "https://intake.local/intake")
        assert is_announcer_enabled() is True

    def test_build_announcement_shape(self):
        body = build_announcement(
            task_id="t1", state="TASK_STATE_SUBMITTED", agent_card_url="https://a/card"
        )
        assert body == {
            "id": "t1",
            "status": {"state": "TASK_STATE_SUBMITTED"},
            "agentCardUrl": "https://a/card",
        }

    def test_build_announcement_includes_tenant_and_update(self):
        body = build_announcement(
            task_id="t1",
            state="TASK_STATE_WORKING",
            agent_card_url="https://a/card",
            update="halfway",
            tenant="acme",
        )
        assert body["tenant"] == "acme"
        assert body["status"]["update"] == "halfway"


class TestAnnouncerBehaviour:
    @pytest.mark.asyncio
    async def test_silent_noop_when_disabled(self, monkeypatch):
        monkeypatch.delenv(ENV_INTAKE_URL, raising=False)
        received: list[dict] = []
        async with _client_for(_intake_app(received)) as client:
            ok = await announce_task(
                task_id="t1",
                state="TASK_STATE_SUBMITTED",
                agent_card_url="https://a/card",
                client=client,
            )
        assert ok is False
        assert received == []

    @pytest.mark.asyncio
    async def test_fires_when_configured(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "http://intake.local/intake")
        received: list[dict] = []
        async with _client_for(_intake_app(received)) as client:
            ok = await announce_task(
                task_id="task-42",
                state="TASK_STATE_SUBMITTED",
                agent_card_url="https://selva/card",
                tenant="acme",
                client=client,
            )
        assert ok is True
        assert len(received) == 1
        assert received[0]["id"] == "task-42"
        assert received[0]["status"]["state"] == "TASK_STATE_SUBMITTED"
        assert received[0]["agentCardUrl"] == "https://selva/card"
        assert received[0]["tenant"] == "acme"

    @pytest.mark.asyncio
    async def test_bearer_token_sent_when_configured(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "http://intake.local/intake")
        monkeypatch.setenv(ENV_INTAKE_TOKEN, "s3cret")
        received: list[dict] = []
        app = _intake_app(received, require_token="s3cret")
        async with _client_for(app) as client:
            ok = await announce_task(
                task_id="t1",
                state="TASK_STATE_SUBMITTED",
                agent_card_url="https://a/card",
                client=client,
            )
        assert ok is True
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_never_raises_on_transport_failure(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "http://intake.local/intake")

        class _BoomTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                raise httpx.ConnectError("boom")

        async with httpx.AsyncClient(
            transport=_BoomTransport(), base_url="http://intake.local"
        ) as client:
            # Must NOT raise; returns False after exhausting retries.
            ok = await announce_task(
                task_id="t1",
                state="TASK_STATE_SUBMITTED",
                agent_card_url="https://a/card",
                attempts=2,
                base_backoff_seconds=0.001,
                client=client,
            )
        assert ok is False

    @pytest.mark.asyncio
    async def test_retries_then_succeeds_on_5xx_then_200(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "http://intake.local/intake")
        calls = {"n": 0}

        class _FlakyTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                calls["n"] += 1
                if calls["n"] == 1:
                    return httpx.Response(503, json={"err": "unavailable"})
                return httpx.Response(200, json={"ok": True})

        async with httpx.AsyncClient(
            transport=_FlakyTransport(), base_url="http://intake.local"
        ) as client:
            ok = await announce_task(
                task_id="t1",
                state="TASK_STATE_SUBMITTED",
                agent_card_url="https://a/card",
                attempts=3,
                base_backoff_seconds=0.001,
                client=client,
            )
        assert ok is True
        assert calls["n"] == 2

    @pytest.mark.asyncio
    async def test_4xx_is_permanent_no_retry(self, monkeypatch):
        monkeypatch.setenv(ENV_INTAKE_URL, "http://intake.local/intake")
        calls = {"n": 0}

        class _ForbiddenTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                calls["n"] += 1
                return httpx.Response(403, json={"err": "forbidden"})

        async with httpx.AsyncClient(
            transport=_ForbiddenTransport(), base_url="http://intake.local"
        ) as client:
            ok = await announce_task(
                task_id="t1",
                state="TASK_STATE_SUBMITTED",
                agent_card_url="https://a/card",
                attempts=3,
                base_backoff_seconds=0.001,
                client=client,
            )
        assert ok is False
        assert calls["n"] == 1  # no retry on 4xx

    @pytest.mark.asyncio
    async def test_run_is_never_blocked_by_announcer_on_timeout(self, monkeypatch):
        # A timed-out intake surfaces as httpx.TimeoutException; announce_task
        # must swallow it and return without propagating (the run continues).
        monkeypatch.setenv(ENV_INTAKE_URL, "http://intake.local/intake")

        class _TimeoutTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                raise httpx.ReadTimeout("intake timed out", request=request)

        async with httpx.AsyncClient(
            transport=_TimeoutTransport(), base_url="http://intake.local"
        ) as client:
            # Bound the whole call so a regression that *does* block fails loudly.
            ok = await asyncio.wait_for(
                announce_task(
                    task_id="t1",
                    state="TASK_STATE_SUBMITTED",
                    agent_card_url="https://a/card",
                    attempts=2,
                    base_backoff_seconds=0.001,
                    client=client,
                ),
                timeout=2.0,
            )
        assert ok is False
