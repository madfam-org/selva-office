"""Local filesystem artifact storage with content-addressable dedup."""

from __future__ import annotations

import os
from pathlib import Path

from .base import ArtifactStorage


class LocalFSStorage(ArtifactStorage):
    """Content-addressable local filesystem storage.

    Layout: ``<base_dir>/<hash[0:2]>/<hash[2:4]>/<hash>``
    """

    def __init__(self, base_dir: str | None = None) -> None:
        self._base = Path(
            base_dir or os.environ.get("ARTIFACT_STORAGE_PATH", "/tmp/autoswarm-artifacts")
        )

    def _hash_path(self, content_hash: str) -> Path:
        return self._base / content_hash[:2] / content_hash[2:4] / content_hash

    async def save(self, content: bytes, content_hash: str) -> str:
        dest = self._hash_path(content_hash)
        if dest.exists():
            return str(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        return str(dest)

    async def retrieve(self, path: str) -> bytes:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"Artifact not found: {path}")
        return p.read_bytes()

    async def delete(self, path: str) -> bool:
        p = Path(path)
        if p.exists():
            p.unlink()
            return True
        return False

    async def exists(self, content_hash: str) -> str | None:
        dest = self._hash_path(content_hash)
        return str(dest) if dest.exists() else None
