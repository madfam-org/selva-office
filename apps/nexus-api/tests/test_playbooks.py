"""Tests for the Playbook CRUD REST API endpoints.

Covers:
- GET  /api/v1/playbooks       (list, includes seeded defaults)
- POST /api/v1/playbooks       (create)
- GET  /api/v1/playbooks/match (event matching)
- GET  /api/v1/playbooks/{id}  (get by ID)
- PATCH /api/v1/playbooks/{id} (update)
- DELETE /api/v1/playbooks/{id} (delete)
- Edge cases: 404s, validation, match miss
"""

from __future__ import annotations

import httpx

# ---------------------------------------------------------------------------
# Seed data verification
# ---------------------------------------------------------------------------


class TestPlaybookSeeds:
    """Verify that the 6 seed playbooks are loaded on startup."""

    async def test_list_returns_seeded_playbooks(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/v1/playbooks")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 6

    async def test_seeded_playbook_names(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/v1/playbooks")
        names = {pb["name"] for pb in resp.json()}
        expected = {
            "Lead Response",
            "Content Publish",
            "Trial Retention",
            "Auto-Restart on Pod Crash",
            "Automated Health Analysis",
            "Database Migration Runner",
        }
        assert expected.issubset(names)

    async def test_seeded_playbooks_have_required_fields(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/v1/playbooks")
        for pb in resp.json():
            assert "id" in pb
            assert "name" in pb
            assert "trigger_event" in pb
            assert "allowed_actions" in pb
            assert "token_budget" in pb
            assert "financial_cap_cents" in pb
            assert "enabled" in pb
            assert "org_id" in pb
            assert "created_at" in pb


# ---------------------------------------------------------------------------
# Create playbook
# ---------------------------------------------------------------------------


class TestCreatePlaybook:
    """POST /api/v1/playbooks"""

    async def test_create_minimal(self, client: httpx.AsyncClient) -> None:
        payload = {
            "name": "Test Playbook",
            "trigger_event": "test:event",
            "allowed_actions": ["api_call"],
        }
        resp = await client.post("/api/v1/playbooks", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test Playbook"
        assert data["trigger_event"] == "test:event"
        assert data["allowed_actions"] == ["api_call"]
        assert data["token_budget"] == 50  # default
        assert data["financial_cap_cents"] == 0  # default
        assert data["require_approval"] is False
        assert data["enabled"] is True

    async def test_create_with_all_fields(self, client: httpx.AsyncClient) -> None:
        payload = {
            "name": "Full Playbook",
            "trigger_event": "billing:overdue",
            "allowed_actions": ["email_send", "api_call", "billing_write"],
            "token_budget": 100,
            "financial_cap_cents": 2000,
            "require_approval": True,
            "enabled": False,
        }
        resp = await client.post("/api/v1/playbooks", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["token_budget"] == 100
        assert data["financial_cap_cents"] == 2000
        assert data["require_approval"] is True
        assert data["enabled"] is False

    async def test_create_missing_required_fields(self, client: httpx.AsyncClient) -> None:
        resp = await client.post("/api/v1/playbooks", json={})
        assert resp.status_code == 422

    async def test_create_name_too_long(self, client: httpx.AsyncClient) -> None:
        payload = {
            "name": "x" * 101,
            "trigger_event": "test:event",
            "allowed_actions": ["api_call"],
        }
        resp = await client.post("/api/v1/playbooks", json=payload)
        assert resp.status_code == 422

    async def test_create_token_budget_out_of_range(self, client: httpx.AsyncClient) -> None:
        payload = {
            "name": "Bad Budget",
            "trigger_event": "test:event",
            "allowed_actions": ["api_call"],
            "token_budget": 0,
        }
        resp = await client.post("/api/v1/playbooks", json=payload)
        assert resp.status_code == 422

    async def test_created_playbook_appears_in_list(self, client: httpx.AsyncClient) -> None:
        payload = {
            "name": "Discoverable Playbook",
            "trigger_event": "test:discoverable",
            "allowed_actions": ["api_call"],
        }
        create_resp = await client.post("/api/v1/playbooks", json=payload)
        assert create_resp.status_code == 201
        created_id = create_resp.json()["id"]

        list_resp = await client.get("/api/v1/playbooks")
        ids = {pb["id"] for pb in list_resp.json()}
        assert created_id in ids


# ---------------------------------------------------------------------------
# Get playbook by ID
# ---------------------------------------------------------------------------


class TestGetPlaybook:
    """GET /api/v1/playbooks/{id}"""

    async def test_get_existing(self, client: httpx.AsyncClient) -> None:
        # Create one first
        create_resp = await client.post(
            "/api/v1/playbooks",
            json={
                "name": "Fetchable",
                "trigger_event": "test:fetch",
                "allowed_actions": ["api_call"],
            },
        )
        pb_id = create_resp.json()["id"]

        resp = await client.get(f"/api/v1/playbooks/{pb_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Fetchable"

    async def test_get_not_found(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/v1/playbooks/nonexistent-id-000")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Match playbook by event
# ---------------------------------------------------------------------------


class TestMatchPlaybook:
    """GET /api/v1/playbooks/match?event=..."""

    async def test_match_existing_event(self, client: httpx.AsyncClient) -> None:
        """Seed data includes a playbook for 'crm:hot_lead'."""
        resp = await client.get("/api/v1/playbooks/match", params={"event": "crm:hot_lead"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["trigger_event"] == "crm:hot_lead"
        assert data["enabled"] is True

    async def test_match_no_matching_event(self, client: httpx.AsyncClient) -> None:
        resp = await client.get("/api/v1/playbooks/match", params={"event": "nonexistent:event"})
        assert resp.status_code == 404

    async def test_match_skips_require_approval_playbooks(self, client: httpx.AsyncClient) -> None:
        """The 'Database Migration Runner' has require_approval=True and should not match."""
        resp = await client.get(
            "/api/v1/playbooks/match",
            params={"event": "infra:migration_pending"},
        )
        assert resp.status_code == 404

    async def test_match_skips_disabled_playbooks(self, client: httpx.AsyncClient) -> None:
        # Create a disabled playbook
        create_resp = await client.post(
            "/api/v1/playbooks",
            json={
                "name": "Disabled PB",
                "trigger_event": "test:disabled_match",
                "allowed_actions": ["api_call"],
                "enabled": False,
            },
        )
        assert create_resp.status_code == 201

        resp = await client.get(
            "/api/v1/playbooks/match",
            params={"event": "test:disabled_match"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update playbook
# ---------------------------------------------------------------------------


class TestUpdatePlaybook:
    """PATCH /api/v1/playbooks/{id}"""

    async def test_update_name(self, client: httpx.AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/playbooks",
            json={
                "name": "Original Name",
                "trigger_event": "test:update",
                "allowed_actions": ["api_call"],
            },
        )
        pb_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/playbooks/{pb_id}",
            json={"name": "Updated Name"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_update_partial(self, client: httpx.AsyncClient) -> None:
        """Only provided fields are updated; others remain unchanged."""
        create_resp = await client.post(
            "/api/v1/playbooks",
            json={
                "name": "Partial Update",
                "trigger_event": "test:partial",
                "allowed_actions": ["api_call", "email_send"],
                "token_budget": 80,
            },
        )
        pb_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/playbooks/{pb_id}",
            json={"token_budget": 200},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token_budget"] == 200
        assert data["name"] == "Partial Update"
        assert data["allowed_actions"] == ["api_call", "email_send"]

    async def test_update_enable_disable(self, client: httpx.AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/playbooks",
            json={
                "name": "Toggle",
                "trigger_event": "test:toggle",
                "allowed_actions": ["api_call"],
            },
        )
        pb_id = create_resp.json()["id"]

        resp = await client.patch(
            f"/api/v1/playbooks/{pb_id}",
            json={"enabled": False},
        )
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_update_not_found(self, client: httpx.AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/playbooks/nonexistent-id",
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete playbook
# ---------------------------------------------------------------------------


class TestDeletePlaybook:
    """DELETE /api/v1/playbooks/{id}"""

    async def test_delete_existing(self, client: httpx.AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/playbooks",
            json={
                "name": "To Delete",
                "trigger_event": "test:delete",
                "allowed_actions": ["api_call"],
            },
        )
        pb_id = create_resp.json()["id"]

        resp = await client.delete(f"/api/v1/playbooks/{pb_id}")
        assert resp.status_code == 204

        # Verify it's gone
        get_resp = await client.get(f"/api/v1/playbooks/{pb_id}")
        assert get_resp.status_code == 404

    async def test_delete_not_found(self, client: httpx.AsyncClient) -> None:
        resp = await client.delete("/api/v1/playbooks/nonexistent-id")
        assert resp.status_code == 404

    async def test_delete_removes_from_list(self, client: httpx.AsyncClient) -> None:
        create_resp = await client.post(
            "/api/v1/playbooks",
            json={
                "name": "Vanishing",
                "trigger_event": "test:vanish",
                "allowed_actions": ["api_call"],
            },
        )
        pb_id = create_resp.json()["id"]

        await client.delete(f"/api/v1/playbooks/{pb_id}")

        list_resp = await client.get("/api/v1/playbooks")
        ids = {pb["id"] for pb in list_resp.json()}
        assert pb_id not in ids
