"""Knowledge Center API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/knowledge", tags=["Knowledge Center"])


class AskRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=500)
    top_k: int = Field(5, ge=1, le=10)
    provider: Literal["default", "ollama"] = "default"
    model: str | None = Field(None, max_length=128)


@router.post("/ask")
async def ask(
    data: AskRequest,
    container: Container = Depends(get_container),
):
    """Document Q&A — retrieve top chunks and answer with citations."""
    return await container.knowledge_service.ask(
        data.question,
        top_k=data.top_k,
        provider=data.provider,
        model=data.model,
    )


@router.get("/llm/models")
async def llm_models(
    container: Container = Depends(get_container),
):
    """List the default LLM and locally available Ollama chat models."""
    return await container.knowledge_service.list_llm_models()


@router.get("/search")
async def search(
    query: str = Query(..., min_length=1, description="Search query"),
    top_k: int = Query(10, ge=1, le=50),
    doc_type: str | None = Query(None, description="Filter by document type"),
    min_score: float = Query(0.0, ge=0.0),
    container: Container = Depends(get_container),
):
    """Hybrid RAG search — dense (vector) + sparse (BM25) fusion."""
    svc = container.knowledge_service
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
                "snippet": r.snippet,
                "highlights": r.highlights,
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
    container: Container = Depends(get_container),
):
    """Search within a specific document."""
    svc = container.knowledge_service
    results = await svc.search_by_document(query=query, document_id=document_id, top_k=top_k)
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
