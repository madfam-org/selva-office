"""Tests for the Phase 6 dispatch audience gate.

POST /api/v1/swarms/dispatch must reject tenant swarms that reference
platform-audience skills in ``required_skills``. Platform swarms (org_id
matches ``PLATFORM_ORG_ID``) can dispatch any audience.

The dev-auth-bypass fixture returns org_id="dev-org", so:
- PLATFORM_ORG_ID="dev-org"  → caller is platform → any skill allowed
- PLATFORM_ORG_ID unset/other → caller is tenant → platform skills forbidden
"""

from __future__ import annotations

import httpx
import pytest

from selva_permissions import PLATFORM_ORG_ID_ENV


def _dispatch_body(*, required_skills: list[str]) -> dict:
    return {
        "description": "audience gate test",
        "graph_type": "coding",
        "required_skills": required_skills,
    }


@pytest.mark.asyncio
class TestAudienceGate:
    async def test_tenant_cannot_dispatch_platform_skill(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # No PLATFORM_ORG_ID → caller (dev-org) is tenant.
        monkeypatch.delenv(PLATFORM_ORG_ID_ENV, raising=False)
        resp = await client.post(
            "/api/v1/swarms/dispatch",
            json=_dispatch_body(required_skills=["cluster-triage"]),
            headers=auth_headers,
        )
        assert resp.status_code == 403, resp.text
        detail = resp.json()["detail"]
        assert detail["error"] == "audience_mismatch"
        assert "cluster-triage" in detail["forbidden_skills"]
        assert detail["caller_audience"] == "tenant"

    async def test_tenant_cannot_dispatch_any_platform_skill(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(PLATFORM_ORG_ID_ENV, raising=False)
        resp = await client.post(
            "/api/v1/swarms/dispatch",
            json=_dispatch_body(
                required_skills=[
                    "cluster-triage",
                    "dns-migration",
                    "tenant-onboarding",
                ]
            ),
            headers=auth_headers,
        )
        assert resp.status_code == 403, resp.text
        forbidden = set(resp.json()["detail"]["forbidden_skills"])
        assert forbidden == {"cluster-triage", "dns-migration", "tenant-onboarding"}

    async def test_platform_can_dispatch_platform_skill(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # PLATFORM_ORG_ID matches dev auth bypass → caller is platform.
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "dev-org")
        resp = await client.post(
            "/api/v1/swarms/dispatch",
            json=_dispatch_body(required_skills=["cluster-triage"]),
            headers=auth_headers,
        )
        # We don't assert 201 here because skill-based agent matching may
        # find no idle agents in the empty test DB and produce other errors.
        # What we DO assert: the response is NOT a 403-audience_mismatch.
        if resp.status_code == 403:
            detail = resp.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") != "audience_mismatch", resp.text

    async def test_tenant_can_dispatch_tenant_skill(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(PLATFORM_ORG_ID_ENV, raising=False)
        resp = await client.post(
            "/api/v1/swarms/dispatch",
            json=_dispatch_body(required_skills=["outbound-voice"]),
            headers=auth_headers,
        )
        # Not a 403 audience mismatch (tenant can use tenant skill)
        if resp.status_code == 403:
            detail = resp.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") != "audience_mismatch", resp.text

    async def test_no_skills_requires_no_gate(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(PLATFORM_ORG_ID_ENV, raising=False)
        resp = await client.post(
            "/api/v1/swarms/dispatch",
            json=_dispatch_body(required_skills=[]),
            headers=auth_headers,
        )
        # Gate should NOT fire on empty skill list
        if resp.status_code == 403:
            detail = resp.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") != "audience_mismatch", resp.text

    async def test_unknown_skill_does_not_trigger_gate(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # An unknown skill name resolves to None in the skill registry;
        # the gate only rejects PLATFORM-tagged skills, so unknown
        # skills pass this check (and fail elsewhere if at all).
        monkeypatch.delenv(PLATFORM_ORG_ID_ENV, raising=False)
        resp = await client.post(
            "/api/v1/swarms/dispatch",
            json=_dispatch_body(required_skills=["does-not-exist"]),
            headers=auth_headers,
        )
        if resp.status_code == 403:
            detail = resp.json().get("detail", {})
            if isinstance(detail, dict):
                assert detail.get("error") != "audience_mismatch", resp.text
