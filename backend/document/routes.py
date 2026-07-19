"""Document Center API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from document.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadResponse,
)
from document.service import DocumentService

router = APIRouter(prefix="/documents", tags=["Document Center"])


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    doc_type: str | None = Form(None),
    company_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Upload a document → parse → chunk → embed → index."""
    content = await file.read()
    svc = DocumentService(db)
    company_uuid = uuid.UUID(company_id) if company_id else None
    doc = await svc.process_upload(
        file_bytes=content,
        filename=file.filename or "unknown",
        title=title,
        doc_type=doc_type,
        company_id=company_uuid,
    )
    return DocumentUploadResponse(
        id=doc.id,
        title=doc.title,
        doc_type=doc.doc_type,
        chunk_count=doc.chunk_count or 0,
        is_indexed=doc.is_indexed,
        message="Document processed and indexed successfully",
    )


@router.get("", response_model=DocumentListResponse)
async def list_documents(
    query: str | None = Query(None, description="Search by title"),
    doc_type: str | None = None,
    company_id: str | None = None,
    is_indexed: bool | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    svc = DocumentService(db)
    company_uuid = uuid.UUID(company_id) if company_id else None
    docs, total = await svc.search(
        query=query,
        doc_type=doc_type,
        company_id=company_uuid,
        is_indexed=is_indexed,
        skip=skip,
        limit=limit,
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(d) for d in docs],
        total=total,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = DocumentService(db)
    doc = await svc.get(document_id)
    return doc


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = DocumentService(db)
    await svc.delete(document_id)
