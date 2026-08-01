"""Embedding adapter — uses Ollama API or sentence-transformers with BGE-M3."""

from __future__ import annotations

import asyncio
from functools import lru_cache

import httpx

from core.config import settings
from core.interfaces import EmbeddingModel
from core.logging import logger

# Shared httpx client with connection pooling. Cached per event loop:
# pytest/TestClient each run requests in their own loop, so a client bound
# to a closed loop must be rebuilt instead of reused.
_embed_client: httpx.AsyncClient | None = None
_embed_client_loop: asyncio.AbstractEventLoop | None = None


async def _get_embed_client() -> httpx.AsyncClient:
    global _embed_client, _embed_client_loop
    loop = asyncio.get_running_loop()
    if _embed_client is None or _embed_client_loop is not loop:
        old = _embed_client
        _embed_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=20),
            proxy=None,
        )
        _embed_client_loop = loop
        if old is not None:
            try:
                await old.aclose()
            except Exception:
                pass
    return _embed_client


class OllamaEmbedding:
    """Embedding via Ollama API — no local model download needed.

    Dimension is auto-discovered from the first embed response and cached.
    If it differs from ``settings.EMBEDDING_DIMENSION`` a warning is logged
    (this catches config drift when swapping models).
    """

    def __init__(
        self,
        model: str = "nomic-embed-text",
        base_url: str = "http://localhost:11434",
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._dim: int | None = None

    @property
    def dimension(self) -> int:
        if self._dim is None:
            self._dim = settings.EMBEDDING_DIMENSION
            if self._dim is None:
                self._dim = 768  # last-resort fallback
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = await _get_embed_client()
        try:
            resp = await client.post(
                f"{self._base_url}/api/embed",
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings")
            if embeddings:
                # ── Auto-discover actual dimension ────────────────
                actual_dim = len(embeddings[0])
                if self._dim is not None and self._dim != actual_dim:
                    logger.warning(
                        "Embedding dimension mismatch: "
                        "config/settings=%d, Ollama '%s' returns %d. "
                        "Overriding to %d — update EMBEDDING_DIMENSION "
                        "in config to silence this warning.",
                        self._dim,
                        self._model,
                        actual_dim,
                        actual_dim,
                    )
                self._dim = actual_dim
                return embeddings
        except Exception:
            logger.warning("Ollama embed API call failed, returning zero vectors")
        # Fallback: return zero vectors
        return [[0.0] * self.dimension for _ in texts]

    async def embed_query(self, text: str) -> list[float]:
        result = await self.embed([text])
        return result[0] if result else []


class SentenceTransformerEmbedding:
    """sentence-transformers based embedding (local, no API calls)."""

    def __init__(
        self,
        model_name: str = settings.EMBEDDING_MODEL,
        device: str = settings.EMBEDDING_DEVICE,
    ) -> None:
        self._model_name = model_name
        self._device = device
        self._model = None  # lazy load

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name, device=self._device)
        return self._model

    @property
    def dimension(self) -> int:
        return self._get_model().get_sentence_embedding_dimension()

    async def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return embeddings.tolist()

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed([text]))[0]


@lru_cache(maxsize=1)
def create_embedding() -> EmbeddingModel:
    """Create embedding model — prefers Ollama, falls back to sentence-transformers."""
    if settings.EMBEDDING_PROVIDER == "ollama":
        try:
            return OllamaEmbedding(
                model=settings.OLLAMA_EMBEDDING_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
            )
        except Exception:
            pass
    return SentenceTransformerEmbedding()
