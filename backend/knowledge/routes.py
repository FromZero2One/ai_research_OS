"""Knowledge Center API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["Knowledge Center"])


@router.get("/search")
async def search(
    query: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(10, ge=1, le=50),
    doc_type: str | None = Query(None, description="Filter by document type"),
    min_score: float = Query(0.0, ge=0.0),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid RAG search — dense (vector) + sparse (BM25) fusion."""
    svc = KnowledgeService(db)
    results = await svc.search(
        query=query,
        top_k=top_k,
        doc_type=doc_type,
        min_score=min_score,
    )
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "content": r.content,
                "score": round(r.score, 4),
                "document_id": r.document_id,
                "chunk_index": r.chunk_index,
                "title": r.title,
                "doc_type": r.doc_type,
            }
            for r in results
        ],
    }


@router.get("/search/document/{document_id}")
async def search_in_document(
    document_id: str,
    query: str = Query(..., min_length=1),
    top_k: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    """Search within a specific document."""
    svc = KnowledgeService(db)
    results = await svc.search_by_document(
        query=query, document_id=document_id, top_k=top_k
    )
    return {
        "query": query,
        "document_id": document_id,
        "count": len(results),
        "results": [
            {
                "content": r.content,
                "score": round(r.score, 4),
                "chunk_index": r.chunk_index,
            }
            for r in results
        ],
    }
