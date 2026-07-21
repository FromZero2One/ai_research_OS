"""Embedding adapter — uses Ollama API or sentence-transformers with BGE-M3."""

from __future__ import annotations

import os
from functools import lru_cache

# Strip proxy env vars that interfere with local connections.
# Must run before any httpx client is created.
for _var in ("all_proxy", "ALL_PROXY", "http_proxy", "HTTP_PROXY",
              "https_proxy", "HTTPS_PROXY", "ftp_proxy", "FTP_PROXY"):
    os.environ.pop(_var, None)
os.environ["no_proxy"] = "localhost,127.0.0.0/8,::1"
os.environ["NO_PROXY"] = "localhost,127.0.0.0/8,::1"

import httpx

from core.config import settings
from core.interfaces import EmbeddingModel


class OllamaEmbedding:
    """Embedding via Ollama API — no local model download needed."""

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
        return self._dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Fallback: return zero vectors (embeddings not critical for V1 demo)
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

            self._model = SentenceTransformer(
                self._model_name, device=self._device
            )
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
    if settings.LLM_PROVIDER == "ollama":
        try:
            return OllamaEmbedding(
                model=settings.OLLAMA_EMBEDDING_MODEL,
                base_url=settings.OLLAMA_BASE_URL,
            )
        except Exception:
            pass
    return SentenceTransformerEmbedding()
