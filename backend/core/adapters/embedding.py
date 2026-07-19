"""Embedding adapter — uses sentence-transformers with BGE-M3."""

from __future__ import annotations

from functools import lru_cache

from core.config import settings
from core.interfaces import EmbeddingModel


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
    return SentenceTransformerEmbedding()
