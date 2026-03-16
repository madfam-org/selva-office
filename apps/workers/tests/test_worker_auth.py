"""Tests for Phase 2: worker auth helper and configurable token."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestGetWorkerAuthHeaders:
    """get_worker_auth_headers returns correctly formatted Authorization header."""

    def test_returns_bearer_header_from_settings(self) -> None:
        mock_settings = MagicMock(worker_api_token="my-secret-token")
        with patch("autoswarm_workers.config.get_settings", return_value=mock_settings):
            from autoswarm_workers.auth import get_worker_auth_headers

            headers = get_worker_auth_headers()
            assert headers == {"Authorization": "Bearer my-secret-token"}

    def test_default_token_is_dev_bypass(self) -> None:
        mock_settings = MagicMock(worker_api_token="dev-bypass")
        with patch("autoswarm_workers.config.get_settings", return_value=mock_settings):
            from autoswarm_workers.auth import get_worker_auth_headers

            headers = get_worker_auth_headers()
            assert headers == {"Authorization": "Bearer dev-bypass"}

    def test_returns_dict_type(self) -> None:
        mock_settings = MagicMock(worker_api_token="token")
        with patch("autoswarm_workers.config.get_settings", return_value=mock_settings):
            from autoswarm_workers.auth import get_worker_auth_headers

            headers = get_worker_auth_headers()
            assert isinstance(headers, dict)
            assert "Authorization" in headers


class TestWorkerApiTokenSetting:
    """worker_api_token field exists on Settings and reads WORKER_API_TOKEN env."""

    def test_default_value(self) -> None:
        with patch.dict("os.environ", {}, clear=False):
            from autoswarm_workers.config import Settings

            s = Settings(
                redis_url="redis://localhost:6379",
                nexus_api_url="http://localhost:4300",
            )
            assert s.worker_api_token == "dev-bypass"

    def test_reads_from_env(self) -> None:
        with patch.dict("os.environ", {"WORKER_API_TOKEN": "prod-jwt-token"}, clear=False):
            from autoswarm_workers.config import Settings

            s = Settings(
                redis_url="redis://localhost:6379",
                nexus_api_url="http://localhost:4300",
            )
            assert s.worker_api_token == "prod-jwt-token"


class TestNoHardcodedDevBypass:
    """Ensure no non-test worker source files contain hardcoded 'Bearer dev-bypass'."""

    def test_no_hardcoded_bearer_in_worker_source(self) -> None:
        from pathlib import Path

        worker_src = Path(__file__).resolve().parent.parent / "autoswarm_workers"
        violations: list[str] = []

        for py_file in worker_src.rglob("*.py"):
            # Skip __pycache__
            if "__pycache__" in str(py_file):
                continue
            content = py_file.read_text()
            if '"Bearer dev-bypass"' in content or "'Bearer dev-bypass'" in content:
                violations.append(str(py_file.relative_to(worker_src)))

        assert violations == [], (
            f"Found hardcoded 'Bearer dev-bypass' in: {violations}. "
            "Use get_worker_auth_headers() instead."
        )
