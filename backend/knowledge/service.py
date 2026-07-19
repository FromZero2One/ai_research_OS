"""Knowledge Center — Hybrid RAG search.

V1: Dense (Qdrant) + Sparse (BM25) reciprocal rank fusion.
No Knowledge Graph — that's V2.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.embedding import create_embedding
from core.adapters.vector_store import create_vector_store
from core.event_service import EventLogger
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


class KnowledgeService:
    """Hybrid RAG retrieval — dense (vector) + sparse (BM25)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.embedder = create_embedding()
        self.vector_store = create_vector_store()
        self._bm25_index: dict[str, "BM25Index"] = {}  # lazy per-collection

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
            collection="documents",
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
            collection="documents",
            vector=query_vector,
            top_k=top_k * 2,
            filter_={"document_id": document_id},
        )
        # Fall back to BM25
        results = await self._enrich_results(vector_results)
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
        bm25 = await self._get_bm25("documents")

        if not bm25 or not query:
            return []

        scores = bm25.get_scores(query.split())
        top_indices = sorted(
            range(len(scores)), key=lambda i: scores[i], reverse=True
        )[:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append({
                    "id": bm25.ids[idx],
                    "score": float(scores[idx]) / 100.0,  # normalize
                    "payload": bm25.metadata[idx],
                })
        return results

    async def _get_bm25(self, collection: str):
        """Build BM25 index from database chunks (lazy)."""
        if collection in self._bm25_index:
            return self._bm25_index[collection]

        from rank_bm25 import BM25Okapi

        result = await self.session.execute(
            select(DocumentChunk).where(
                DocumentChunk.embedding_id.isnot(None)
            )
        )
        chunks = list(result.scalars().all())
        if not chunks:
            return None

        tokenized_corpus = [c.content.split() for c in chunks]
        bm25 = BM25Okapi(tokenized_corpus)
        bm25.ids = [c.embedding_id for c in chunks]
        bm25.metadata = [
            {
                "document_id": str(c.document_id),
                "chunk_index": c.chunk_index,
            }
            for c in chunks
        ]

        self._bm25_index[collection] = bm25  # type: ignore[assignment]
        return bm25

    def _rrf_fusion(
        self,
        dense: list,
        sparse: list,
        k: int = 60,
    ) -> list:
        """Reciprocal Rank Fusion — combine dense and sparse results."""
        scores: Counter = Counter()

        for rank, result in enumerate(dense):
            doc_id = result.id
            scores[doc_id] += 1.0 / (k + rank + 1)

        for rank, result in enumerate(sparse):
            doc_id = result["id"]
            scores[doc_id] += 1.0 / (k + rank + 1)

        return [
            {"id": doc_id, "score": score}
            for doc_id, score in scores.most_common()
        ]

    async def _enrich_results(
        self, fused: list[dict]
    ) -> list[SearchResult]:
        """Enrich fused results with full chunk content from DB."""
        if not fused:
            return []

        enriched = []
        for item in fused:
            embedding_id = item["id"]
            result = await self.session.execute(
                select(DocumentChunk, Document)
                .join(Document, DocumentChunk.document_id == Document.id)
                .where(DocumentChunk.embedding_id == embedding_id)
            )
            row = result.one_or_none()
            if row:
                chunk, doc = row
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

    async def _db_text_search(
        self, query: str, document_id: str, top_k: int
    ) -> list[SearchResult]:
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
