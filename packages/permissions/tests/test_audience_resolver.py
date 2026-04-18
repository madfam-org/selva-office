"""Tests for the audience resolver (phase 4)."""

from __future__ import annotations

import pytest

from selva_permissions import (
    PLATFORM_ORG_ID_ENV,
    Audience,
    get_platform_org_id,
    is_platform_audience,
    resolve_audience,
)


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a clean env state."""
    monkeypatch.delenv(PLATFORM_ORG_ID_ENV, raising=False)


class TestGetPlatformOrgId:
    def test_unset_returns_none(self) -> None:
        assert get_platform_org_id() is None

    def test_empty_string_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "")
        assert get_platform_org_id() is None

    def test_whitespace_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "  \t ")
        assert get_platform_org_id() is None

    def test_set_returns_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "madfam-internal")
        assert get_platform_org_id() == "madfam-internal"


class TestResolveAudience:
    def test_no_platform_config_is_always_tenant(self) -> None:
        # Safe default — if PLATFORM_ORG_ID isn't set, nobody is platform.
        assert resolve_audience("madfam-internal") is Audience.TENANT
        assert resolve_audience("some-customer") is Audience.TENANT
        assert resolve_audience(None) is Audience.TENANT

    def test_matching_org_is_platform(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "madfam-internal")
        assert resolve_audience("madfam-internal") is Audience.PLATFORM

    def test_non_matching_org_is_tenant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "madfam-internal")
        assert resolve_audience("some-customer") is Audience.TENANT

    def test_none_org_id_is_tenant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "madfam-internal")
        assert resolve_audience(None) is Audience.TENANT

    def test_empty_org_id_is_tenant(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "madfam-internal")
        assert resolve_audience("") is Audience.TENANT


class TestIsPlatformAudience:
    def test_matches_resolve(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(PLATFORM_ORG_ID_ENV, "madfam-internal")
        assert is_platform_audience("madfam-internal") is True
        assert is_platform_audience("some-customer") is False

    def test_no_config_is_false(self) -> None:
        assert is_platform_audience("madfam-internal") is False
