"""Tests for Phase 2 tail primitives: stripe_connect + selva_office_provisioning.

Same pattern as test_phase2_tenant_primitives — registry shape, credential
gating, happy path, error bubble-up using module-level ``_request`` mocks.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from selva_tools.builtins.selva_office_provisioning import (
    SelvaOfficeSeatCreateTool,
    SelvaOfficeSeatRevokeTool,
    get_selva_office_provisioning_tools,
)
from selva_tools.builtins.stripe_connect import (
    StripeConnectAccountCreateTool,
    StripeConnectAccountLinkTool,
    StripeConnectAccountStatusTool,
    get_stripe_connect_tools,
)


class TestRegistries:
    def test_stripe_connect_three_tools(self) -> None:
        assert {t.name for t in get_stripe_connect_tools()} == {
            "stripe_connect_account_create",
            "stripe_connect_account_link",
            "stripe_connect_account_status",
        }

    def test_office_provisioning_three_tools(self) -> None:
        assert {t.name for t in get_selva_office_provisioning_tools()} == {
            "selva_office_seat_create",
            "selva_office_seat_assign_department",
            "selva_office_seat_revoke",
        }


@pytest.mark.asyncio
class TestCredentialGating:
    async def test_stripe_connect_fails_without_key(self) -> None:
        with patch.object(
            __import__(
                "selva_tools.builtins.stripe_connect",
                fromlist=["STRIPE_SECRET_KEY"],
            ),
            "STRIPE_SECRET_KEY",
            "",
        ):
            res = await StripeConnectAccountCreateTool().execute(
                email="a@b.c",
                business_type="company",
                return_url="https://x",
                refresh_url="https://y",
            )
            assert not res.success
            assert "STRIPE_SECRET_KEY" in (res.error or "")

    async def test_stripe_connect_fails_on_malformed_key(self) -> None:
        with patch.object(
            __import__(
                "selva_tools.builtins.stripe_connect",
                fromlist=["STRIPE_SECRET_KEY"],
            ),
            "STRIPE_SECRET_KEY",
            "not-a-stripe-key",
        ):
            res = await StripeConnectAccountStatusTool().execute(account_id="acct_x")
            assert not res.success
            assert "malformed" in (res.error or "").lower()

    async def test_office_seat_create_fails_without_token(self) -> None:
        with patch.object(
            __import__(
                "selva_tools.builtins.selva_office_provisioning",
                fromlist=["WORKER_API_TOKEN"],
            ),
            "WORKER_API_TOKEN",
            "",
        ):
            res = await SelvaOfficeSeatCreateTool().execute(
                org_id="org-1",
                user_sub="u-1",
                display_name="Alice",
                email="alice@x.com",
            )
            assert not res.success
            assert "WORKER_API_TOKEN" in (res.error or "")


@pytest.mark.asyncio
class TestStripeConnectHappyPath:
    async def test_account_create_returns_onboarding_url(self) -> None:
        # Two _request calls: POST /accounts then POST /account_links.
        mock = AsyncMock(
            side_effect=[
                (200, {"id": "acct_123"}),
                (
                    200,
                    {
                        "url": "https://connect.stripe.com/setup/xyz",
                        "expires_at": 1800000000,
                    },
                ),
            ]
        )
        with (
            patch(
                "selva_tools.builtins.stripe_connect.STRIPE_SECRET_KEY",
                "sk_test_dummy",
            ),
            patch("selva_tools.builtins.stripe_connect._request", mock),
        ):
            res = await StripeConnectAccountCreateTool().execute(
                email="ops@tenant.com",
                business_type="company",
                return_url="https://app.madfam.io/onboard/done",
                refresh_url="https://app.madfam.io/onboard/refresh",
                country="MX",
            )
            assert res.success, res.error
            assert res.data["account_id"] == "acct_123"
            assert "connect.stripe.com" in res.data["onboarding_url"]
            assert res.data["country"] == "MX"

    async def test_account_link_regenerates(self) -> None:
        mock = AsyncMock(
            return_value=(
                200,
                {
                    "url": "https://connect.stripe.com/setup/refresh",
                    "expires_at": 1800000999,
                },
            )
        )
        with (
            patch(
                "selva_tools.builtins.stripe_connect.STRIPE_SECRET_KEY",
                "sk_test_dummy",
            ),
            patch("selva_tools.builtins.stripe_connect._request", mock),
        ):
            res = await StripeConnectAccountLinkTool().execute(
                account_id="acct_123",
                return_url="https://r",
                refresh_url="https://f",
            )
            assert res.success, res.error
            assert res.data["account_id"] == "acct_123"
            assert "refresh" in res.data["onboarding_url"]

    async def test_account_status_reports_requirements(self) -> None:
        mock = AsyncMock(
            return_value=(
                200,
                {
                    "charges_enabled": False,
                    "payouts_enabled": False,
                    "details_submitted": True,
                    "requirements": {
                        "currently_due": ["individual.id_number", "tos_acceptance.date"],
                        "past_due": [],
                        "disabled_reason": "requirements.past_due",
                    },
                },
            )
        )
        with (
            patch(
                "selva_tools.builtins.stripe_connect.STRIPE_SECRET_KEY",
                "sk_test_dummy",
            ),
            patch("selva_tools.builtins.stripe_connect._request", mock),
        ):
            res = await StripeConnectAccountStatusTool().execute(account_id="acct_123")
            assert res.success, res.error
            assert res.data["charges_enabled"] is False
            assert res.data["currently_due"] == [
                "individual.id_number",
                "tos_acceptance.date",
            ]

    async def test_account_create_bubbles_stripe_error(self) -> None:
        mock = AsyncMock(
            return_value=(
                400,
                {"error": {"message": "country not supported", "code": "country_invalid"}},
            )
        )
        with (
            patch(
                "selva_tools.builtins.stripe_connect.STRIPE_SECRET_KEY",
                "sk_test_dummy",
            ),
            patch("selva_tools.builtins.stripe_connect._request", mock),
        ):
            res = await StripeConnectAccountCreateTool().execute(
                email="x@y.z",
                business_type="company",
                return_url="https://r",
                refresh_url="https://f",
                country="XX",
            )
            assert not res.success
            assert "country not supported" in (res.error or "")


@pytest.mark.asyncio
class TestSelvaOfficeHappyPath:
    async def test_seat_create(self) -> None:
        mock = AsyncMock(return_value=(201, {"seat_id": "seat-7"}))
        with (
            patch(
                "selva_tools.builtins.selva_office_provisioning.WORKER_API_TOKEN",
                "dev-bypass",
            ),
            patch("selva_tools.builtins.selva_office_provisioning._request", mock),
        ):
            res = await SelvaOfficeSeatCreateTool().execute(
                org_id="tenant-1",
                user_sub="user-42",
                display_name="Telar",
                email="telar@tenant.com",
                role="manager",
                department_id="dept-engineering",
            )
            assert res.success, res.error
            assert res.data["seat_id"] == "seat-7"
            assert res.data["role"] == "manager"

    async def test_seat_revoke_requires_reason(self) -> None:
        mock = AsyncMock(return_value=(204, {}))
        with (
            patch(
                "selva_tools.builtins.selva_office_provisioning.WORKER_API_TOKEN",
                "dev-bypass",
            ),
            patch("selva_tools.builtins.selva_office_provisioning._request", mock),
        ):
            res = await SelvaOfficeSeatRevokeTool().execute(seat_id="seat-7", reason="offboarded")
            assert res.success, res.error
            assert res.data["reason"] == "offboarded"

    async def test_seat_create_bubbles_api_error(self) -> None:
        mock = AsyncMock(
            return_value=(
                409,
                {"detail": "seat already exists for this (org, user_sub)"},
            )
        )
        with (
            patch(
                "selva_tools.builtins.selva_office_provisioning.WORKER_API_TOKEN",
                "dev-bypass",
            ),
            patch("selva_tools.builtins.selva_office_provisioning._request", mock),
        ):
            res = await SelvaOfficeSeatCreateTool().execute(
                org_id="t", user_sub="u", display_name="d", email="e@f.g"
            )
            assert not res.success
            assert "already exists" in (res.error or "")
