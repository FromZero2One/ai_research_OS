"""BGE Reranker adapter — cross-encoder re-ranking for search results.

Uses BAAI/bge-reranker-v2-m3 or similar cross-encoder models via sentence-transformers.
Re-ranks the top-N results from hybrid search to improve precision.
"""

from __future__ import annotations

from functools import lru_cache

from core.config import settings


class BGEReranker:
    """Cross-encoder re-ranker using BGE-Reranker models.

    Takes a query and candidate documents, returns re-ranked results
    with improved relevance scores.
    """

    MODEL_NAME = "BAAI/bge-reranker-v2-m3"

    def __init__(self, device: str = settings.EMBEDDING_DEVICE) -> None:
        self._device = device
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                self.MODEL_NAME,
                device=self._device,
                trust_remote_code=True,
            )
        return self._model

    async def rerank(
        self,
        query: str,
        documents: list[tuple[str, str, dict]],  # (content, title, metadata)
        top_k: int | None = None,
    ) -> list[tuple[float, str, dict]]:
        """Re-rank documents by relevance to the query.

        Args:
            query: The search query.
            documents: List of (content, title, metadata) tuples.
            top_k: Number of results to return (default: all).

        Returns:
            List of (score, content, metadata) sorted by relevance descending.
        """
        if not documents:
            return []

        import asyncio

        def _sync_rerank() -> list[tuple[float, str, dict]]:
            model = self._get_model()
            pairs = [
                [query, f"{title}\n{content[:512]}"]
                for content, title, _ in documents
            ]
            scores = model.predict(pairs, show_progress_bar=False)
            scored = list(zip(scores.tolist() if hasattr(scores, 'tolist') else scores, documents))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [
                (float(score), content, meta)
                for score, (content, _, meta) in scored
            ]

        results = await asyncio.to_thread(_sync_rerank)
        if top_k:
            results = results[:top_k]
        return results


@lru_cache(maxsize=1)
def create_reranker() -> BGEReranker:
    """Create a singleton reranker instance."""
    return BGEReranker()
