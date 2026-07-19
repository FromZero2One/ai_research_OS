"""Document Center Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentCreate(BaseModel):
    title: str = Field(..., max_length=512)
    doc_type: str = Field(..., max_length=64)
    source: str | None = None
    company_id: UUID | None = None
    extra_metadata: dict | None = Field(default=None, alias="extra_metadata")


class DocumentResponse(BaseModel):
    id: UUID
    title: str
    doc_type: str
    source: str | None
    company_id: UUID | None
    file_path: str | None
    file_size_bytes: int | None
    mime_type: str | None
    chunk_count: int | None
    is_indexed: bool
    extra_metadata: dict | None = None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True, "populate_by_name": True}


class DocumentChunkResponse(BaseModel):
    id: UUID
    chunk_index: int
    content: str
    token_count: int | None
    embedding_id: str | None

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int


class DocumentUploadResponse(BaseModel):
    id: UUID
    title: str
    doc_type: str
    chunk_count: int
    is_indexed: bool
    message: str
