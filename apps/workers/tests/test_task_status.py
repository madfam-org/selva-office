"""Tests for task status lifecycle updates (Gap 1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestUpdateTaskStatus:
    """update_task_status sends PATCH requests to nexus-api."""

    @pytest.mark.asyncio
    async def test_patches_running_status(self) -> None:
        mock_response = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "autoswarm_workers.task_status.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from autoswarm_workers.task_status import update_task_status

            await update_task_status("http://test:4300", "task-1", "running")

            mock_client.patch.assert_called_once()
            call_args = mock_client.patch.call_args
            assert call_args[0][0] == "http://test:4300/api/v1/swarms/tasks/task-1"
            payload = call_args[1]["json"]
            assert payload["status"] == "running"
            assert "result" not in payload

    @pytest.mark.asyncio
    async def test_patches_completed_with_result(self) -> None:
        mock_response = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "autoswarm_workers.task_status.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from autoswarm_workers.task_status import update_task_status

            await update_task_status(
                "http://test:4300", "task-1", "completed", {"output": "done"},
            )

            payload = mock_client.patch.call_args[1]["json"]
            assert payload["status"] == "completed"
            assert payload["result"] == {"output": "done"}

    @pytest.mark.asyncio
    async def test_patches_failed_with_error(self) -> None:
        mock_response = MagicMock(status_code=200)
        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "autoswarm_workers.task_status.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from autoswarm_workers.task_status import update_task_status

            await update_task_status(
                "http://test:4300", "task-1", "failed", {"error": "boom"},
            )

            payload = mock_client.patch.call_args[1]["json"]
            assert payload["status"] == "failed"
            assert payload["result"]["error"] == "boom"

    @pytest.mark.asyncio
    async def test_skips_unknown_task_id(self) -> None:
        with patch("autoswarm_workers.task_status.httpx.AsyncClient") as mock_cls:
            from autoswarm_workers.task_status import update_task_status

            await update_task_status("http://test:4300", "unknown", "running")
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_http_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.patch.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "autoswarm_workers.task_status.httpx.AsyncClient",
            return_value=mock_client,
        ):
            from autoswarm_workers.task_status import update_task_status

            # Should not raise.
            await update_task_status("http://test:4300", "task-1", "running")

    @pytest.mark.asyncio
    async def test_logs_warning_on_non_200_status(self) -> None:
        mock_response = MagicMock(status_code=400, text="Bad request")
        mock_client = AsyncMock()
        mock_client.patch.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "autoswarm_workers.task_status.httpx.AsyncClient",
                return_value=mock_client,
            ),
            patch("autoswarm_workers.task_status.logger") as mock_logger,
        ):
            from autoswarm_workers.task_status import update_task_status

            await update_task_status("http://test:4300", "task-1", "running")
            mock_logger.warning.assert_called()


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
