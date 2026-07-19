"""Portfolio Center Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    name: str = Field(..., max_length=256)
    description: str | None = None


class WatchlistResponse(WatchlistCreate):
    id: UUID
    items: list[WatchlistItemResponse] = []
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class WatchlistItemCreate(BaseModel):
    ticker: str = Field(..., max_length=16)
    notes: str | None = None
    target_price: float | None = None
    reason: str | None = None


class WatchlistItemResponse(WatchlistItemCreate):
    id: UUID
    watchlist_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class HoldingCreate(BaseModel):
    ticker: str = Field(..., max_length=16)
    shares: float = Field(..., gt=0)
    avg_cost_basis: float | None = None
    sector: str | None = None
    notes: str | None = None


class HoldingUpdate(BaseModel):
    shares: float | None = Field(None, gt=0)
    avg_cost_basis: float | None = None
    sector: str | None = None
    notes: str | None = None
    is_active: bool | None = None


class HoldingResponse(HoldingCreate):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class JournalEntryCreate(BaseModel):
    entry_type: str = Field(..., pattern="^(idea|analysis|reflection|lesson)$")
    ticker: str | None = Field(None, max_length=16)
    title: str = Field(..., max_length=512)
    content: str = Field(..., min_length=10)
    tags: list[str] | None = None
    research_session_id: UUID | None = None


class JournalEntryResponse(JournalEntryCreate):
    id: UUID
    tags: dict | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
