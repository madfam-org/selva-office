"""Abstract base class for artifact storage backends."""

from __future__ import annotations

import abc


class ArtifactStorage(abc.ABC):
    """Interface for persisting and retrieving artifact content."""

    @abc.abstractmethod
    async def save(self, content: bytes, content_hash: str) -> str:
        """Persist content and return the storage path.

        Implementations should deduplicate: if a file with the same hash
        already exists, return its path without re-writing.
        """

    @abc.abstractmethod
    async def retrieve(self, path: str) -> bytes:
        """Retrieve content by storage path.

        Raises:
            FileNotFoundError: If the path does not exist.
        """

    @abc.abstractmethod
    async def delete(self, path: str) -> bool:
        """Delete content at the given storage path. Returns True if deleted."""

    @abc.abstractmethod
    async def exists(self, content_hash: str) -> str | None:
        """Check if content with the given hash exists. Returns path or None."""
