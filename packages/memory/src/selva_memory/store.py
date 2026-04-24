"""Per-agent memory store backed by pgvector for semantic search."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Column, String, delete, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .embeddings import DEFAULT_DIM, EmbeddingProvider

logger = logging.getLogger(__name__)

Base = declarative_base()


class MemoryEntryModel(Base):
    __tablename__ = "agent_memories"
    id = Column(String, primary_key=True)
    agent_id = Column(String, index=True, nullable=False)
    text = Column(String, nullable=False)
    metadata_ = Column("metadata", JSON, nullable=False)
    created_at = Column(String, nullable=False)
    embedding = Column(Vector(DEFAULT_DIM))


@dataclass
class MemoryEntry:
    """A single memory entry with text, metadata, and vector embedding."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    agent_id: str = ""


class MemoryStore:
    """Per-agent semantic memory store using pgvector for similarity search.

    Replaces previous FAISS implementation to handle scaling and persistence
    natively via PostgreSQL.
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

        # Read database url from env, fallback to default docker-compose url
        db_url = os.getenv(
            "DATABASE_URL", "postgresql+asyncpg://autoswarm:autoswarm@localhost:5432/autoswarm"
        )
        # Ensure driver is asyncpg
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        self._engine = create_async_engine(db_url, echo=False)
        self._session_factory = sessionmaker(
            self._engine, class_=AsyncSession, expire_on_commit=False
        )

    async def _init_db(self) -> None:
        async with self._engine.begin() as conn:
            # Check if pgvector extension is available, create if needed
            await conn.execute(select(1))  # Just a ping
            # Note: Extension creation requires superuser, assuming it's done via migration or root
            await conn.run_sync(Base.metadata.create_all)

    async def store(self, text: str, metadata: dict[str, Any] | None = None) -> str:
        """Store a memory entry. Returns the entry ID."""
        await self._init_db()
        entry_id = str(uuid.uuid4())
        created_at = datetime.now(UTC).isoformat()

        vector = await self._embedder.embed_single(text)

        db_entry = MemoryEntryModel(
            id=entry_id,
            agent_id=self.agent_id,
            text=text,
            metadata_=metadata or {},
            created_at=created_at,
            embedding=vector,
        )

        async with self._session_factory() as session:
            session.add(db_entry)
            await session.commit()

        logger.debug("Stored memory for agent %s: %s", self.agent_id, entry_id)
        return entry_id

    async def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """Search for memories similar to the query text."""
        await self._init_db()
        query_vector = await self._embedder.embed_single(query)

        async with self._session_factory() as session:
            # Using inner product (<#>) which matches FAISS IndexFlatIP
            stmt = (
                select(MemoryEntryModel)
                .filter(MemoryEntryModel.agent_id == self.agent_id)
                .order_by(MemoryEntryModel.embedding.cosine_distance(query_vector))
                .limit(top_k)
            )
            result = await session.execute(stmt)
            result.scalars().all()

            # pgvector doesn't return distance directly in simple
            # selects, so we need a tuple. Adjust to get distance:
            dist_col = MemoryEntryModel.embedding.cosine_distance(
                query_vector,
            ).label("distance")
            stmt_with_dist = (
                select(MemoryEntryModel, dist_col)
                .filter(MemoryEntryModel.agent_id == self.agent_id)
                .order_by("distance")
                .limit(top_k)
            )
            result_dist = await session.execute(stmt_with_dist)

            results = []
            for row, distance in result_dist:
                meta = dict(row.metadata_)
                # Convert cosine distance back to a similarity score if matched FAISS
                meta["_similarity_score"] = 1.0 - float(distance)

                results.append(
                    MemoryEntry(
                        id=row.id,
                        text=row.text,
                        metadata=meta,
                        created_at=row.created_at,
                        agent_id=row.agent_id,
                    )
                )

            return results

    async def list_entries(
        self, filter_metadata: dict[str, Any] | None = None
    ) -> list[MemoryEntry]:
        """List all entries, optionally filtered by metadata keys.

        In an async pgvector context, this signature is ideally
        awaited. But if keeping synchronous signature compatibility
        is strict, this might fail unless used safely. Here we
        implement the async version assuming clients will adapt.
        """
        await self._init_db()
        async with self._session_factory() as session:
            stmt = select(MemoryEntryModel).filter(MemoryEntryModel.agent_id == self.agent_id)
            result = await session.execute(stmt)
            rows = result.scalars().all()

            entries = []
            for row in rows:
                if filter_metadata and not all(
                    row.metadata_.get(k) == v for k, v in filter_metadata.items()
                ):
                    continue
                entries.append(
                    MemoryEntry(
                        id=row.id,
                        text=row.text,
                        metadata=row.metadata_,
                        created_at=row.created_at,
                        agent_id=row.agent_id,
                    )
                )
            return entries

    async def delete(self, entry_ids: list[str]) -> int:
        """Delete entries by ID. Returns count of deleted entries."""
        if not entry_ids:
            return 0
        await self._init_db()
        async with self._session_factory() as session:
            stmt = (
                delete(MemoryEntryModel)
                .where(MemoryEntryModel.id.in_(entry_ids))
                .where(MemoryEntryModel.agent_id == self.agent_id)
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    @property
    def count(self) -> int:
        """This property is synchronous and shouldn't hit DB directly in async pg context.
        As a fallback, it returns 0 or needs to be swapped for an async `get_count()`.
        """
        return 0

    def _save(self) -> None:
        pass

    def _load(self) -> None:
        pass
