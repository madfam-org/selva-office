"""Tests for event emitter and instrumented_node decorator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_MOCK_AUTH = {"Authorization": "Bearer test-token"}


def _patch_auth():
    """Patch get_worker_auth_headers for event_emitter calls."""
    return patch(
        "selva_workers.auth.get_worker_auth_headers",
        return_value=_MOCK_AUTH,
    )


# ---------------------------------------------------------------------------
# emit_event tests
# ---------------------------------------------------------------------------


class TestEmitEvent:
    """emit_event fires POST to nexus-api (via fire_and_forget_request) and PUBLISH to Redis."""

    @pytest.mark.asyncio
    async def test_posts_to_nexus_url_with_correct_body(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ffr,
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
                task_id="task-1",
                agent_id="agent-1",
            )

            mock_ffr.assert_called_once()
            call_args = mock_ffr.call_args
            assert call_args[0][0] == "POST"
            assert call_args[0][1] == "http://test:4300/api/v1/events/"
            payload = call_args[1]["json"]
            assert payload["event_type"] == "node.entered"
            assert payload["event_category"] == "node"
            assert payload["task_id"] == "task-1"
            assert payload["agent_id"] == "agent-1"

    @pytest.mark.asyncio
    async def test_includes_auth_headers(self) -> None:
        """Verify that emit_event passes auth headers to fire_and_forget_request."""
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ffr,
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
            )

            assert mock_ffr.call_args[1]["headers"] == _MOCK_AUTH

    @pytest.mark.asyncio
    async def test_includes_optional_fields_when_provided(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ffr,
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            await emit_event(
                "http://test:4300",
                event_type="inference.completed",
                event_category="inference",
                task_id="task-2",
                agent_id="agent-2",
                node_id="plan",
                graph_type="coding",
                payload={"key": "value"},
                duration_ms=150,
                provider="anthropic",
                model="claude-sonnet-4-6",
                token_count=500,
                error_message="partial failure",
                request_id="req-abc",
            )

            payload = mock_ffr.call_args[1]["json"]
            assert payload["node_id"] == "plan"
            assert payload["graph_type"] == "coding"
            assert payload["payload"] == {"key": "value"}
            assert payload["duration_ms"] == 150
            assert payload["provider"] == "anthropic"
            assert payload["model"] == "claude-sonnet-4-6"
            assert payload["token_count"] == 500
            assert payload["error_message"] == "partial failure"
            assert payload["request_id"] == "req-abc"

    @pytest.mark.asyncio
    async def test_skips_task_id_when_unknown(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ffr,
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
                task_id="unknown",
            )

            payload = mock_ffr.call_args[1]["json"]
            assert "task_id" not in payload

    @pytest.mark.asyncio
    async def test_skips_agent_id_when_unknown(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ffr,
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
                agent_id="unknown",
            )

            payload = mock_ffr.call_args[1]["json"]
            assert "agent_id" not in payload

    @pytest.mark.asyncio
    async def test_uses_2s_http_timeout(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ffr,
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
            )

            assert mock_ffr.call_args[1]["timeout"] == 2.0

    @pytest.mark.asyncio
    async def test_publishes_to_redis_channel(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import EVENTS_CHANNEL, emit_event

            await emit_event(
                "http://test:4300",
                event_type="node.exited",
                event_category="node",
                task_id="task-1",
            )

            mock_pool.execute_with_retry.assert_called_once()
            call_args = mock_pool.execute_with_retry.call_args
            assert call_args[0][0] == "publish"
            assert call_args[0][1] == EVENTS_CHANNEL
            broadcast = json.loads(call_args[0][2])
            assert broadcast["event_type"] == "node.exited"
            assert broadcast["task_id"] == "task-1"
            assert "id" in broadcast
            assert "created_at" in broadcast

    @pytest.mark.asyncio
    async def test_handles_redis_failure_gracefully(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock(side_effect=Exception("Redis down"))

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ),
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            patch("selva_workers.event_emitter.logger") as mock_logger,
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            # Should not raise.
            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
            )

            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_sets_org_id_only_when_not_default(self) -> None:
        mock_pool = MagicMock()
        mock_pool.execute_with_retry = AsyncMock()

        with (
            patch(
                "selva_workers.event_emitter.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ffr,
            patch(
                "selva_workers.event_emitter.get_redis_pool",
                return_value=mock_pool,
            ),
            _patch_auth(),
        ):
            from selva_workers.event_emitter import emit_event

            # Default org_id should be omitted.
            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
                org_id="default",
            )
            payload_default = mock_ffr.call_args[1]["json"]
            assert "org_id" not in payload_default

            mock_ffr.reset_mock()

            # Non-default org_id should be included.
            await emit_event(
                "http://test:4300",
                event_type="node.entered",
                event_category="node",
                org_id="acme-corp",
            )
            payload_custom = mock_ffr.call_args[1]["json"]
            assert payload_custom["org_id"] == "acme-corp"


# ---------------------------------------------------------------------------
# instrumented_node tests
# ---------------------------------------------------------------------------


class TestInstrumentedNode:
    """instrumented_node decorator emits lifecycle events around graph nodes."""

    def test_emits_entered_then_exited(self) -> None:
        emitted: list[dict] = []

        async def _capture_emit(_nexus_url, **kwargs):  # type: ignore[no-untyped-def]
            emitted.append(kwargs)

        with (
            patch(
                "selva_workers.event_emitter.emit_event",
                side_effect=_capture_emit,
            ),
            patch(
                "selva_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def my_node(state):  # type: ignore[no-untyped-def]
                return {"status": "ok"}

            result = my_node({"task_id": "t1", "agent_id": "a1"})

            assert result == {"status": "ok"}

            event_types = [e["event_type"] for e in emitted]
            assert event_types[0] == "node.entered"
            assert event_types[1] == "node.exited"

    def test_measures_duration_ms(self) -> None:
        emitted: list[dict] = []

        async def _capture_emit(_nexus_url, **kwargs):  # type: ignore[no-untyped-def]
            emitted.append(kwargs)

        with (
            patch(
                "selva_workers.event_emitter.emit_event",
                side_effect=_capture_emit,
            ),
            patch(
                "selva_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def slow_node(state):  # type: ignore[no-untyped-def]
                return state

            slow_node({"task_id": "t1"})

            exited_events = [e for e in emitted if e["event_type"] == "node.exited"]
            assert len(exited_events) == 1
            assert "duration_ms" in exited_events[0]
            assert isinstance(exited_events[0]["duration_ms"], int)
            assert exited_events[0]["duration_ms"] >= 0

    def test_extracts_task_id_from_state_dict(self) -> None:
        emitted: list[dict] = []

        async def _capture_emit(_nexus_url, **kwargs):  # type: ignore[no-untyped-def]
            emitted.append(kwargs)

        with (
            patch(
                "selva_workers.event_emitter.emit_event",
                side_effect=_capture_emit,
            ),
            patch(
                "selva_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def plan(state):  # type: ignore[no-untyped-def]
                return state

            plan({"task_id": "task-42", "agent_id": "a1"})

            for event in emitted:
                assert event["task_id"] == "task-42"

    def test_extracts_agent_id_from_state_dict(self) -> None:
        emitted: list[dict] = []

        async def _capture_emit(_nexus_url, **kwargs):  # type: ignore[no-untyped-def]
            emitted.append(kwargs)

        with (
            patch(
                "selva_workers.event_emitter.emit_event",
                side_effect=_capture_emit,
            ),
            patch(
                "selva_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def implement(state):  # type: ignore[no-untyped-def]
                return state

            implement({"task_id": "t1", "agent_id": "agent-7"})

            for event in emitted:
                assert event["agent_id"] == "agent-7"

    def test_emits_node_error_on_exception_and_reraises(self) -> None:
        emitted: list[dict] = []

        async def _capture_emit(_nexus_url, **kwargs):  # type: ignore[no-untyped-def]
            emitted.append(kwargs)

        with (
            patch(
                "selva_workers.event_emitter.emit_event",
                side_effect=_capture_emit,
            ),
            patch(
                "selva_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def failing_node(state):  # type: ignore[no-untyped-def]
                raise ValueError("something broke")

            with pytest.raises(ValueError, match="something broke"):
                failing_node({"task_id": "t1"})

            error_events = [e for e in emitted if e["event_type"] == "node.error"]
            assert len(error_events) == 1
            assert "something broke" in error_events[0]["error_message"]
            assert "duration_ms" in error_events[0]

    def test_preserves_function_name(self) -> None:
        with patch(
            "selva_workers.config.get_settings",
            return_value=MagicMock(nexus_api_url="http://test:4300"),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def review(state):  # type: ignore[no-untyped-def]
                return state

            assert review.__name__ == "review"
            assert review.__wrapped__.__name__ == "review"  # type: ignore[attr-defined]

    def test_handles_non_dict_state_gracefully(self) -> None:
        emitted: list[dict] = []

        async def _capture_emit(_nexus_url, **kwargs):  # type: ignore[no-untyped-def]
            emitted.append(kwargs)

        with (
            patch(
                "selva_workers.event_emitter.emit_event",
                side_effect=_capture_emit,
            ),
            patch(
                "selva_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def odd_node(state):  # type: ignore[no-untyped-def]
                return state

            result = odd_node("not-a-dict")

            assert result == "not-a-dict"

            # All events should fall back to "unknown" for task_id/agent_id.
            for event in emitted:
                assert event["task_id"] == "unknown"
                assert event["agent_id"] == "unknown"

    def test_returns_original_function_return_value(self) -> None:
        emitted: list[dict] = []

        async def _capture_emit(_nexus_url, **kwargs):  # type: ignore[no-untyped-def]
            emitted.append(kwargs)

        with (
            patch(
                "selva_workers.event_emitter.emit_event",
                side_effect=_capture_emit,
            ),
            patch(
                "selva_workers.config.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
        ):
            from selva_workers.event_emitter import instrumented_node

            @instrumented_node
            def compute(state):  # type: ignore[no-untyped-def]
                return {"status": "completed", "files": ["a.py", "b.py"]}

            result = compute({"task_id": "t1"})

            assert result == {"status": "completed", "files": ["a.py", "b.py"]}
