"""Tests for approval audit trail (responded_by field)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_approval_request(status="pending"):
    """Create a mock ApprovalRequest."""
    req = MagicMock()
    req.id = uuid.uuid4()
    req.agent_id = uuid.uuid4()
    req.action_category = "git_push"
    req.action_type = "git_push"
    req.payload = {}
    req.diff = None
    req.reasoning = "test"
    req.urgency = "medium"
    req.status = status
    req.feedback = None
    req.responded_by = None
    req.org_id = "default"
    req.created_at = datetime.now(UTC)
    req.responded_at = None
    return req


@pytest.mark.asyncio
async def test_approve_stores_responded_by():
    """Approving a request sets responded_by to the user's sub claim."""
    from nexus_api.routers.approvals import _respond_to_request

    req = _make_approval_request()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = req

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    with (
        patch(
            "nexus_api.routers.approvals.manager",
            MagicMock(
                send_approval_response=AsyncMock(),
            ),
        ),
        patch("nexus_api.routers.approvals.notify_approval_decision", new_callable=AsyncMock),
    ):
        result = await _respond_to_request(
            str(req.id),
            "approved",
            "looks good",
            db,
            responded_by="user-123",
        )

    assert req.responded_by == "user-123"
    assert result.responded_by == "user-123"


@pytest.mark.asyncio
async def test_deny_stores_responded_by():
    """Denying a request sets responded_by to the user's sub claim."""
    from nexus_api.routers.approvals import _respond_to_request

    req = _make_approval_request()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = req

    db = AsyncMock()
    db.execute = AsyncMock(return_value=mock_result)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    with (
        patch(
            "nexus_api.routers.approvals.manager",
            MagicMock(
                send_approval_response=AsyncMock(),
            ),
        ),
        patch("nexus_api.routers.approvals.notify_approval_decision", new_callable=AsyncMock),
    ):
        result = await _respond_to_request(
            str(req.id),
            "denied",
            "needs changes",
            db,
            responded_by="admin-456",
        )

    assert req.responded_by == "admin-456"
    assert result.responded_by == "admin-456"
