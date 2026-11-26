"""Company Pydantic schemas — read-only responses (CRUD retired)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class CompanyResponse(BaseModel):
    id: UUID
    ticker: str
    name: str
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    headquarters: str | None = None
    website: str | None = None
    is_active: bool
    priority: int
    target_price: float | None = None
    reason: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
