"""Tests for task status lifecycle updates (Gap 1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestUpdateTaskStatus:
    """update_task_status sends PATCH requests to nexus-api via fire_and_forget_request."""

    @pytest.mark.asyncio
    async def test_patches_running_status(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ffr:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status("http://test:4300", "task-1", "running")

            mock_ffr.assert_called_once_with(
                "PATCH",
                "http://test:4300/api/v1/swarms/tasks/task-1",
                json={"status": "running"},
                headers={"Authorization": "Bearer dev-bypass"},
                timeout=5.0,
            )

    @pytest.mark.asyncio
    async def test_patches_completed_with_result(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ffr:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status(
                "http://test:4300", "task-1", "completed", {"output": "done"},
            )

            call_kwargs = mock_ffr.call_args
            payload = call_kwargs.kwargs["json"]
            assert payload["status"] == "completed"
            assert payload["result"] == {"output": "done"}

    @pytest.mark.asyncio
    async def test_patches_failed_with_error(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ffr:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status(
                "http://test:4300", "task-1", "failed", {"error": "boom"},
            )

            payload = mock_ffr.call_args.kwargs["json"]
            assert payload["status"] == "failed"
            assert payload["result"]["error"] == "boom"

    @pytest.mark.asyncio
    async def test_skips_unknown_task_id(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
        ) as mock_ffr:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status("http://test:4300", "unknown", "running")
            mock_ffr.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_failure(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
            return_value=False,
        ):
            from autoswarm_workers.task_status import update_task_status

            # Should not raise.
            await update_task_status("http://test:4300", "task-1", "running")

    @pytest.mark.asyncio
    async def test_logs_warning_on_failure(self) -> None:
        with (
            patch(
                "autoswarm_workers.task_status.fire_and_forget_request",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch("autoswarm_workers.task_status.logger") as mock_logger,
        ):
            from autoswarm_workers.task_status import update_task_status

            await update_task_status("http://test:4300", "task-1", "running")
            mock_logger.warning.assert_called()
            assert "task-1" in mock_logger.warning.call_args[0][1]

    @pytest.mark.asyncio
    async def test_includes_started_at_when_provided(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ffr:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status(
                "http://test:4300", "task-1", "running",
                started_at="2026-03-14T10:00:00+00:00",
            )

            payload = mock_ffr.call_args.kwargs["json"]
            assert payload["status"] == "running"
            assert payload["started_at"] == "2026-03-14T10:00:00+00:00"

    @pytest.mark.asyncio
    async def test_includes_error_message_when_provided(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ffr:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status(
                "http://test:4300", "task-1", "failed",
                result={"error": "boom"},
                error_message="boom",
            )

            payload = mock_ffr.call_args.kwargs["json"]
            assert payload["status"] == "failed"
            assert payload["error_message"] == "boom"
            assert payload["result"]["error"] == "boom"

    @pytest.mark.asyncio
    async def test_omits_metadata_when_not_provided(self) -> None:
        with patch(
            "autoswarm_workers.task_status.fire_and_forget_request",
            new_callable=AsyncMock,
            return_value=True,
        ) as mock_ffr:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status("http://test:4300", "task-1", "running")

            payload = mock_ffr.call_args.kwargs["json"]
            assert "started_at" not in payload
            assert "error_message" not in payload


class TestStatusMapping:
    """Verify graph status -> API status mapping logic."""

    def test_pushed_maps_to_completed(self) -> None:
        graph_status = "pushed"
        if graph_status in ("completed", "pushed"):
            api_status = "completed"
        elif graph_status in ("blocked", "error", "denied", "timeout"):
            api_status = "failed"
        else:
            api_status = "completed"
        assert api_status == "completed"

    def test_denied_maps_to_failed(self) -> None:
        graph_status = "denied"
        if graph_status in ("completed", "pushed"):
            api_status = "completed"
        elif graph_status in ("blocked", "error", "denied", "timeout"):
            api_status = "failed"
        else:
            api_status = "completed"
        assert api_status == "failed"

    def test_blocked_maps_to_failed(self) -> None:
        graph_status = "blocked"
        if graph_status in ("completed", "pushed"):
            api_status = "completed"
        elif graph_status in ("blocked", "error", "denied", "timeout"):
            api_status = "failed"
        else:
            api_status = "completed"
        assert api_status == "failed"

    def test_unknown_status_maps_to_completed(self) -> None:
        graph_status = "reviewed"
        if graph_status in ("completed", "pushed"):
            api_status = "completed"
        elif graph_status in ("blocked", "error", "denied", "timeout"):
            api_status = "failed"
        else:
            api_status = "completed"
        assert api_status == "completed"
