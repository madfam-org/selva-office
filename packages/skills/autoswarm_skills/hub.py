"""
Track D1: agentskills.io REST client
Mirrors Hermes' agent/skills_hub.py — browse, search, and install community skills.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_HUB_BASE_URL = os.environ.get("AGENTSKILLS_HUB_URL", "https://agentskills.io/api/v1")
_HUB_TIMEOUT = 15.0


@dataclass
class HubSkill:
    name: str
    description: str
    author: str
    version: str
    category: str
    downloads: int
    url: str
    tags: list[str]


class SkillsHubClient:
    """
    REST client for the agentskills.io community hub.

    Falls back gracefully if the hub is unreachable — returns empty results
    rather than raising, so the platform stays operational offline.
    """

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("AGENTSKILLS_API_KEY", "")

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def browse(self, category: str | None = None, page: int = 1) -> list[HubSkill]:
        """Browse skills on the hub, optionally filtered by category."""
        params: dict[str, Any] = {"page": page, "per_page": 20}
        if category:
            params["category"] = category
        return await self._get("/skills", params)

    async def search(self, query: str) -> list[HubSkill]:
        """Full-text search the hub."""
        return await self._get("/skills/search", {"q": query, "per_page": 10})

    async def install(self, skill_name: str, target_dir: str | Path) -> Path:
        """
        Download a skill from the hub and install it into *target_dir*.
        Returns the path of the installed skill directory.
        """
        import httpx

        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=_HUB_TIMEOUT) as client:
            # Get skill metadata
            resp = await client.get(
                f"{_HUB_BASE_URL}/skills/{skill_name}",
                headers=self._auth_headers(),
            )
            resp.raise_for_status()
            skill_data = resp.json()
            download_url = skill_data.get("download_url")
            if not download_url:
                raise ValueError(f"No download_url for skill '{skill_name}'")

            # Download the skill archive
            archive_resp = await client.get(download_url)
            archive_resp.raise_for_status()

        # Extract
        import io
        import tarfile
        import zipfile
        content = archive_resp.content
        skill_dir = target_dir / skill_name
        skill_dir.mkdir(exist_ok=True)

        try:
            with tarfile.open(fileobj=io.BytesIO(content)) as tar:
                tar.extractall(skill_dir)
        except tarfile.TarError:
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    zf.extractall(skill_dir)
            except zipfile.BadZipFile:
                # Assume raw Python file
                (skill_dir / f"{skill_name}.py").write_bytes(content)

        logger.info("SkillsHubClient: installed '%s' to %s", skill_name, skill_dir)
        return skill_dir

    async def publish(self, skill_path: str | Path, token: str) -> dict:
        """Publish a local skill to the hub (requires a hub API token)."""
        import httpx
        skill_path = Path(skill_path)
        if not skill_path.exists():
            raise FileNotFoundError(f"Skill not found: {skill_path}")

        with open(skill_path, "rb") as f:
            content = f.read()

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{_HUB_BASE_URL}/skills",
                headers={"Authorization": f"Bearer {token}", **self._auth_headers()},
                files={"skill": (skill_path.name, content, "application/octet-stream")},
            )
            resp.raise_for_status()
            return resp.json()

    async def _get(self, path: str, params: dict | None = None) -> list[HubSkill]:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=_HUB_TIMEOUT) as client:
                resp = await client.get(
                    f"{_HUB_BASE_URL}{path}",
                    headers=self._auth_headers(),
                    params=params or {},
                )
                resp.raise_for_status()
                data = resp.json()
                fallback = data if isinstance(data, list) else []
                skills = data.get("skills", fallback) if isinstance(data, dict) else data
                return [
                    HubSkill(
                        name=s.get("name", ""),
                        description=s.get("description", ""),
                        author=s.get("author", ""),
                        version=s.get("version", "0.0.0"),
                        category=s.get("category", "general"),
                        downloads=s.get("downloads", 0),
                        url=s.get("url", ""),
                        tags=s.get("tags", []),
                    )
                    for s in skills
                ]
        except Exception as exc:
            logger.warning("SkillsHubClient: hub request failed: %s", exc)
            return []
