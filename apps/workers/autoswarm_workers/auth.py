"""Worker-to-API authentication helpers."""

from __future__ import annotations


def get_worker_auth_headers() -> dict[str, str]:
    """Return Authorization headers for worker-to-API calls.

    Reads the token from ``WORKER_API_TOKEN`` env var (via settings).
    """
    from .config import get_settings

    return {"Authorization": f"Bearer {get_settings().worker_api_token}"}
