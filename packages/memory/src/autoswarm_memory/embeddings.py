"""Embedding providers for vector search — supports OpenAI, Anthropic, and local fallback."""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Default embedding dimension (matches text-embedding-3-small)
DEFAULT_DIM = 1536


class EmbeddingProvider:
    """Generates text embeddings for FAISS indexing.

    Tries external providers (OpenAI, Ollama) in order, falls back to
    a deterministic hash-based embedding for development/testing.
    """

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim
        self._provider: str | None = None
        self._detect_provider()

    def _detect_provider(self) -> None:
        if os.environ.get("OPENAI_API_KEY"):
            self._provider = "openai"
        elif os.environ.get("OLLAMA_BASE_URL"):
            self._provider = "ollama"
        else:
            self._provider = "hash"
            logger.info("No embedding provider configured; using hash-based fallback")

    async def embed(self, texts: list[str]) -> np.ndarray:
        """Embed a list of texts into vectors.

        Returns:
            numpy array of shape (len(texts), self.dim)
        """
        if self._provider == "openai":
            return await self._embed_openai(texts)
        if self._provider == "ollama":
            return await self._embed_ollama(texts)
        return self._embed_hash(texts)

    async def embed_single(self, text: str) -> np.ndarray:
        """Embed a single text string."""
        result = await self.embed([text])
        return result[0]

    def _embed_hash(self, texts: list[str]) -> np.ndarray:
        """Deterministic hash-based embedding for dev/testing."""
        vectors = []
        for text in texts:
            h = hashlib.sha256(text.encode()).digest()
            # Expand hash to fill the embedding dimension
            rng = np.random.default_rng(int.from_bytes(h[:8], "big"))
            vec = rng.standard_normal(self.dim).astype(np.float32)
            # Normalize to unit length
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            vectors.append(vec)
        return np.array(vectors, dtype=np.float32)

    async def _embed_openai(self, texts: list[str]) -> np.ndarray:
        import httpx

        api_key = os.environ.get("OPENAI_API_KEY", "")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "input": texts,
                        "model": "text-embedding-3-small",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = [d["embedding"] for d in data["data"]]
                return np.array(embeddings, dtype=np.float32)
        except Exception:
            logger.warning("OpenAI embedding failed; falling back to hash", exc_info=True)
            return self._embed_hash(texts)

    async def _embed_ollama(self, texts: list[str]) -> np.ndarray:
        import httpx

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        vectors: list[Any] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for text in texts:
                    resp = await client.post(
                        f"{base_url}/api/embeddings",
                        json={"model": "nomic-embed-text", "prompt": text},
                    )
                    resp.raise_for_status()
                    vectors.append(resp.json()["embedding"])
            return np.array(vectors, dtype=np.float32)
        except Exception:
            logger.warning("Ollama embedding failed; falling back to hash", exc_info=True)
            return self._embed_hash(texts)


_instance: EmbeddingProvider | None = None


def get_embedding_provider(dim: int = DEFAULT_DIM) -> EmbeddingProvider:
    """Get the singleton embedding provider."""
    global _instance  # noqa: PLW0603
    if _instance is None:
        _instance = EmbeddingProvider(dim=dim)
    return _instance
