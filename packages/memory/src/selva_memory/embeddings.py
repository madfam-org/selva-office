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

    When an org config specifies a custom embedding provider and model,
    those are used instead of the default OpenAI text-embedding-3-small.
    """

    def __init__(
        self,
        dim: int = DEFAULT_DIM,
        *,
        provider_name: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.dim = dim
        self._provider: str | None = None
        self._embedding_model = model
        self._embedding_base_url = base_url
        self._detect_provider(provider_name)

    def _detect_provider(self, preferred: str | None = None) -> None:
        if preferred and preferred != "openai":
            # Custom provider (e.g. deepinfra) using OpenAI-compatible API
            self._provider = "openai_compat"
        elif os.environ.get("OPENAI_API_KEY"):
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
        if self._provider == "openai_compat":
            return await self._embed_openai_compat(texts)
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
        model = self._embedding_model or "text-embedding-3-small"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "input": texts,
                        "model": model,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = [d["embedding"] for d in data["data"]]
                return np.array(embeddings, dtype=np.float32)
        except Exception:
            logger.warning("OpenAI embedding failed; falling back to hash", exc_info=True)
            return self._embed_hash(texts)

    async def _embed_openai_compat(self, texts: list[str]) -> np.ndarray:
        """Use an OpenAI-compatible endpoint (e.g. DeepInfra) for embeddings."""
        import httpx

        base_url = self._embedding_base_url or "https://api.openai.com/v1"
        model = self._embedding_model or "text-embedding-3-small"

        # Try to resolve the API key from the provider's config
        api_key = ""
        try:
            from madfam_inference.org_config import load_org_config

            org_config = load_org_config()
            provider_name = None
            for name, cfg in org_config.providers.items():
                if cfg.base_url.rstrip("/") == base_url.rstrip("/"):
                    provider_name = name
                    api_key = os.environ.get(cfg.api_key_env, "")
                    break
            if not api_key and provider_name:
                # Fallback: try PROVIDER_API_KEY env var convention
                api_key = os.environ.get(f"{provider_name.upper()}_API_KEY", "")
        except Exception:
            pass

        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{base_url.rstrip('/')}/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "input": texts,
                        "model": model,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                embeddings = [d["embedding"] for d in data["data"]]
                return np.array(embeddings, dtype=np.float32)
        except Exception:
            logger.warning(
                "OpenAI-compat embedding failed (base_url=%s); falling back to hash",
                base_url, exc_info=True,
            )
            return self._embed_hash(texts)

    async def _embed_ollama(self, texts: list[str]) -> np.ndarray:
        import httpx

        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        model = self._embedding_model or "nomic-embed-text"
        vectors: list[Any] = []
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                for text in texts:
                    resp = await client.post(
                        f"{base_url}/api/embeddings",
                        json={"model": model, "prompt": text},
                    )
                    resp.raise_for_status()
                    vectors.append(resp.json()["embedding"])
            return np.array(vectors, dtype=np.float32)
        except Exception:
            logger.warning("Ollama embedding failed; falling back to hash", exc_info=True)
            return self._embed_hash(texts)


_instance: EmbeddingProvider | None = None


def get_embedding_provider(
    dim: int = DEFAULT_DIM,
    *,
    provider_name: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> EmbeddingProvider:
    """Get the singleton embedding provider.

    When called without explicit overrides, attempts to load embedding
    config from the org config file.
    """
    global _instance  # noqa: PLW0603
    if _instance is None:
        # Try loading embedding config from org config
        if provider_name is None and model is None:
            try:
                from madfam_inference.org_config import load_org_config

                org_config = load_org_config()
                if org_config.embedding_provider != "openai" or \
                   org_config.embedding_model != "text-embedding-3-small":
                    provider_name = org_config.embedding_provider
                    model = org_config.embedding_model
                    # Resolve base_url from provider config
                    if provider_name in org_config.providers:
                        base_url = org_config.providers[provider_name].base_url
            except Exception:
                pass

        _instance = EmbeddingProvider(
            dim=dim,
            provider_name=provider_name,
            model=model,
            base_url=base_url,
        )
    return _instance
