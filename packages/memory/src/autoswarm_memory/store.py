"""Per-agent memory store backed by FAISS for semantic search."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import faiss

from .embeddings import DEFAULT_DIM, EmbeddingProvider

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """A single memory entry with text, metadata, and vector embedding."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    agent_id: str = ""


class MemoryStore:
    """Per-agent semantic memory store using FAISS for similarity search.

    Each agent gets an isolated FAISS index. Indexes can persist to disk.
    """

    def __init__(
        self,
        agent_id: str,
        embedding_provider: EmbeddingProvider,
        dim: int = DEFAULT_DIM,
        persist_dir: str | None = None,
    ) -> None:
        self.agent_id = agent_id
        self._embedder = embedding_provider
        self._dim = dim
        self._persist_dir = Path(persist_dir) if persist_dir else None

        # FAISS index + parallel metadata storage
        self._index = faiss.IndexFlatIP(dim)  # Inner product (cosine after normalization)
        self._entries: list[MemoryEntry] = []

        # Try loading from disk
        if self._persist_dir:
            self._load()

    async def store(self, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Store a memory entry. Returns the entry ID."""
        entry = MemoryEntry(
            text=text,
            metadata=metadata or {},
            agent_id=self.agent_id,
        )

        # Embed and add to FAISS
        vector = await self._embedder.embed_single(text)
        self._index.add(vector.reshape(1, -1))
        self._entries.append(entry)

        # Persist
        self._save()

        logger.debug("Stored memory for agent %s: %s", self.agent_id, entry.id)
        return entry.id

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Search for memories similar to the query text."""
        if self._index.ntotal == 0:
            return []

        query_vector = await self._embedder.embed_single(query)
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(query_vector.reshape(1, -1), k)

        results = []
        for idx, score in zip(indices[0], scores[0], strict=False):
            if idx < 0 or idx >= len(self._entries):
                continue
            entry = self._entries[idx]
            entry.metadata["_similarity_score"] = float(score)
            results.append(entry)

        return results

    def list_entries(
        self, filter_metadata: dict[str, Any] | None = None
    ) -> list[MemoryEntry]:
        """List all entries, optionally filtered by metadata keys."""
        if not filter_metadata:
            return list(self._entries)

        return [
            e
            for e in self._entries
            if all(e.metadata.get(k) == v for k, v in filter_metadata.items())
        ]

    def delete(self, entry_ids: list[str]) -> int:
        """Delete entries by ID. Returns count of deleted entries.

        Note: FAISS doesn't support deletion natively. We rebuild the index
        using the hash-based (synchronous) embedding fallback.
        """
        ids_set = set(entry_ids)
        remaining = [e for e in self._entries if e.id not in ids_set]
        deleted = len(self._entries) - len(remaining)

        if deleted == 0:
            return 0

        # Rebuild index using synchronous hash embedding
        self._entries = remaining
        self._index = faiss.IndexFlatIP(self._dim)
        if remaining:
            vectors = self._embedder._embed_hash([e.text for e in remaining])
            self._index.add(vectors)

        self._save()
        return deleted

    @property
    def count(self) -> int:
        return len(self._entries)

    def _save(self) -> None:
        """Persist index and metadata to disk."""
        if not self._persist_dir:
            return
        agent_dir = self._persist_dir / self.agent_id
        agent_dir.mkdir(parents=True, exist_ok=True)

        faiss.write_index(self._index, str(agent_dir / "index.faiss"))

        entries_data = [
            {
                "id": e.id,
                "text": e.text,
                "metadata": e.metadata,
                "created_at": e.created_at,
                "agent_id": e.agent_id,
            }
            for e in self._entries
        ]
        (agent_dir / "entries.json").write_text(
            json.dumps(entries_data, indent=2), encoding="utf-8"
        )

    def _load(self) -> None:
        """Load index and metadata from disk."""
        if not self._persist_dir:
            return
        agent_dir = self._persist_dir / self.agent_id
        index_path = agent_dir / "index.faiss"
        entries_path = agent_dir / "entries.json"

        if not index_path.exists() or not entries_path.exists():
            return

        try:
            self._index = faiss.read_index(str(index_path))
            entries_data = json.loads(entries_path.read_text(encoding="utf-8"))
            self._entries = [
                MemoryEntry(**e) for e in entries_data
            ]
            logger.info(
                "Loaded %d memories for agent %s", len(self._entries), self.agent_id
            )
        except Exception:
            logger.warning(
                "Failed to load memory store for agent %s", self.agent_id, exc_info=True
            )
