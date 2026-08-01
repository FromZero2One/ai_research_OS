"""Knowledge Center — Hybrid RAG search.

V1: Dense (Qdrant) + Sparse (BM25) reciprocal rank fusion.
No Knowledge Graph — that's V2.
"""

from __future__ import annotations

from dataclasses import dataclass

import jieba
from rank_bm25 import BM25Okapi
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.embedding import create_embedding
from core.adapters.reranker import create_reranker
from core.adapters.vector_store import create_vector_store
from core.config import settings
from core.event_service import EventLogger
from core.interfaces import EmbeddingModel, VectorStore
from core.logging import logger
from document.models import Document, DocumentChunk


@dataclass
class SearchResult:
    """Unified search result from hybrid retrieval."""

    content: str
    score: float
    document_id: str
    chunk_index: int
    title: str
    doc_type: str


# Module-level BM25 cache (shared across requests, rebuilt on TTL expiry).
# This avoids loading all chunks from DB on every search request.
_bm25_cache: dict[str, BM25Okapi] = {}
_bm25_cache_time: dict[str, float] = {}
BM25_CACHE_TTL = 300  # seconds before rebuild


class KnowledgeService:
    """Hybrid RAG retrieval — dense (vector) + sparse (BM25)."""

    def __init__(
        self,
        session: AsyncSession,
        use_reranker: bool = False,
        embedder: EmbeddingModel | None = None,
        vector_store: VectorStore | None = None,
        reranker=None,
    ) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.embedder = embedder or create_embedding()
        self.vector_store = vector_store or create_vector_store()
        self._reranker = reranker or (create_reranker() if use_reranker else None)

    async def search(
        self,
        query: str,
        top_k: int = 10,
        doc_type: str | None = None,
        min_score: float = 0.0,
    ) -> list[SearchResult]:
        """Hybrid search: Qdrant (dense) + BM25 (sparse) → RRF fusion."""
        if not query.strip():
            return []

        # Build filter for doc_type
        vector_filter = {"doc_type": doc_type} if doc_type else None

        # 1. Dense search
        query_vector = await self.embedder.embed_query(query)
        dense_results = await self.vector_store.search(
            collection=settings.QDRANT_COLLECTION,
            vector=query_vector,
            top_k=top_k * 2,
            filter_=vector_filter,
        )

        # 2. Sparse search (BM25)
        sparse_results = await self._sparse_search(query, top_k * 2, doc_type)

        # 3. Reciprocal Rank Fusion
        fused = self._rrf_fusion(dense_results, sparse_results, top_k)

        # 4. Enrich with DB content
        enriched = await self._enrich_results(fused)

        # 5. Cross-encoder re-ranking (if available)
        if self._reranker and enriched:
            try:
                docs_for_rerank = [
                    (
                        r.content,
                        r.title,
                        {
                            "document_id": r.document_id,
                            "chunk_index": r.chunk_index,
                            "title": r.title,
                            "doc_type": r.doc_type,
                        },
                    )
                    for r in enriched[: top_k * 3]  # re-rank top 3x
                ]
                reranked = await self._reranker.rerank(query, docs_for_rerank, top_k=top_k)
                enriched = [
                    SearchResult(
                        content=content,
                        score=score,
                        document_id=meta["document_id"],
                        chunk_index=meta["chunk_index"],
                        title=meta["title"],
                        doc_type=meta["doc_type"],
                    )
                    for score, content, meta in reranked
                ]
            except Exception:
                logger.warning("Reranker failed, falling back to RRF")
                pass

        # Log query
        await self.events.record(
            source="knowledge",
            event_type="search.executed",
            payload={
                "query": query[:200],
                "top_k": top_k,
                "results_count": len(enriched),
            },
        )

        return enriched[:top_k]

    async def search_by_document(
        self,
        query: str,
        document_id: str,
        top_k: int = 5,
    ) -> list[SearchResult]:
        """Search within a single document."""
        query_vector = await self.embedder.embed_query(query)
        vector_results = await self.vector_store.search(
            collection=settings.QDRANT_COLLECTION,
            vector=query_vector,
            top_k=top_k * 2,
            filter_={"document_id": document_id},
        )
        # Fall back to BM25
        fused = [{"id": r.id, "score": r.score or 0.0} for r in vector_results]
        results = await self._enrich_results(fused)
        # If not enough, do direct DB text search
        if len(results) < top_k:
            db_results = await self._db_text_search(query, document_id, top_k)
            existing_ids = {r.document_id for r in results}
            for r in db_results:
                if r.document_id not in existing_ids:
                    results.append(r)
        return results[:top_k]

    async def _sparse_search(
        self, query: str, top_k: int, doc_type: str | None = None
    ) -> list[dict]:
        """BM25 sparse search over all indexed chunks."""
        # Load BM25 index (lazy, cached per session)
        bm25 = await self._get_bm25(settings.QDRANT_COLLECTION)

        if not bm25 or not query:
            return []

        scores = bm25.get_scores(jieba.lcut(query))
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append(
                    {
                        "id": bm25.ids[idx],
                        "score": float(scores[idx]) / 100.0,  # normalize
                        "payload": bm25.metadata[idx],
                    }
                )
        return results

    async def _get_bm25(self, collection: str):
        """Build BM25 index from database chunks (module-level cache with TTL)."""
        import time as _time

        now = _time.time()
        cache_age = (
            now - _bm25_cache_time.get(collection, 0)
            if collection in _bm25_cache_time
            else float("inf")
        )

        if collection in _bm25_cache and cache_age < BM25_CACHE_TTL:
            return _bm25_cache[collection]

        logger.info(
            "BM25 cache miss for '%s' (age=%.1fs) — rebuilding from DB",
            collection,
            cache_age,
        )

        # Load the full corpus via keyset pagination — no silent truncation.
        chunks: list[DocumentChunk] = []
        last_id = None
        while True:
            stmt = select(DocumentChunk).where(DocumentChunk.embedding_id.isnot(None))
            if last_id is not None:
                stmt = stmt.where(DocumentChunk.id > last_id)
            stmt = stmt.order_by(DocumentChunk.id).limit(5000)
            batch = list((await self.session.execute(stmt)).scalars().all())
            if not batch:
                break
            chunks.extend(batch)
            last_id = batch[-1].id
            max_chunks = settings.BM25_MAX_CHUNKS
            if max_chunks and len(chunks) >= max_chunks:
                logger.warning(
                    "BM25 corpus truncated at %d chunks (BM25_MAX_CHUNKS=%d)",
                    len(chunks),
                    max_chunks,
                )
                break
        if not chunks:
            return None

        tokenized_corpus = [jieba.lcut(c.content) for c in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25.ids = [c.embedding_id for c in chunks]
        bm25.metadata = [
            {
                "document_id": str(c.document_id),
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]

        _bm25_cache[collection] = bm25  # type: ignore[assignment]
        _bm25_cache_time[collection] = now
        return bm25

    def _rrf_fusion(
        self,
        dense: list,
        sparse: list,
        k: int = 60,
    ) -> list:
        """Reciprocal Rank Fusion — combine dense and sparse results."""
        scores: dict[str, float] = {}

        for rank, result in enumerate(dense):
            doc_id = result.id
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

        for rank, result in enumerate(sparse):
            doc_id = result["id"]
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [{"id": doc_id, "score": score} for doc_id, score in ranked]

    async def _enrich_results(self, fused: list[dict]) -> list[SearchResult]:
        """Enrich fused results with full chunk content from DB."""
        if not fused:
            return []

        # Batch query: one IN fetch instead of N individual queries
        embedding_ids = [item["id"] for item in fused]
        result = await self.session.execute(
            select(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.embedding_id.in_(embedding_ids))
        )
        rows = result.all()

        # Build lookup: embedding_id → (chunk, doc)
        chunk_map: dict[str, tuple] = {}
        for chunk, doc in rows:
            chunk_map[chunk.embedding_id] = (chunk, doc)

        enriched = []
        for item in fused:
            pair = chunk_map.get(item["id"])
            if pair:
                chunk, doc = pair
                enriched.append(
                    SearchResult(
                        content=chunk.content,
                        score=item["score"],
                        document_id=str(doc.id),
                        chunk_index=chunk.chunk_index,
                        title=doc.title,
                        doc_type=doc.doc_type,
                    )
                )
        return enriched

    async def _db_text_search(self, query: str, document_id: str, top_k: int) -> list[SearchResult]:
        """Fallback: direct LIKE search on document chunks."""
        from sqlalchemy import text

        stmt = text("""
            SELECT dc.content, dc.chunk_index, d.title, d.doc_type
            FROM document.document_chunks dc
            JOIN document.documents d ON d.id = dc.document_id
            WHERE dc.document_id = :doc_id
              AND dc.content ILIKE :query
            ORDER BY dc.chunk_index
            LIMIT :limit
        """)
        result = await self.session.execute(
            stmt,
            {
                "doc_id": document_id,
                "query": f"%{query}%",
                "limit": top_k,
            },
        )
        rows = result.all()
        return [
            SearchResult(
                content=row[0],
                score=0.5,
                document_id=document_id,
                chunk_index=row[1],
                title=row[2],
                doc_type=row[3],
            )
            for row in rows
        ]
