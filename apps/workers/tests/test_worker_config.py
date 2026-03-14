"""Tests for worker Settings configuration."""

from __future__ import annotations


class TestWorkerSettings:
    """Settings class handles .env extras gracefully."""

    def test_extra_ignore_allows_unknown_fields(self) -> None:
        """Settings with extra='ignore' should not crash on unknown env vars."""
        from autoswarm_workers.config import Settings

        # Simulate nexus-api-specific vars that would appear in a shared .env
        settings = Settings(
            _env_file=None,
            JANUA_ISSUER_URL="https://auth.example.com",  # type: ignore[call-arg]
            COLYSEUS_SECRET="test-secret",  # type: ignore[call-arg]
            UNKNOWN_VAR="should-be-ignored",  # type: ignore[call-arg]
        )
        assert settings.redis_url == "redis://localhost:6379"

    def test_known_fields_still_parsed(self) -> None:
        """Known fields are still correctly parsed."""
        from autoswarm_workers.config import Settings

        settings = Settings(
            _env_file=None,
            redis_url="redis://custom:6380",
            github_token="gh-test-token",
        )
        assert settings.redis_url == "redis://custom:6380"
        assert settings.github_token == "gh-test-token"
