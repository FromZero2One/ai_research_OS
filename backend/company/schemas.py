"""Company Center Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CompanyTagResponse(BaseModel):
    id: UUID
    tag: str

    model_config = {"from_attributes": True}


class CompanyCreate(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=16, description="Stock ticker symbol")
    name: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    headquarters: str | None = None
    founded_year: int | None = None
    employees: int | None = None
    website: str | None = None
    tags: list[str] = Field(default_factory=list)


class CompanyUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    headquarters: str | None = None
    founded_year: int | None = None
    employees: int | None = None
    website: str | None = None
    is_active: bool | None = None
    tags: list[str] | None = None


class CompanyResponse(BaseModel):
    id: UUID
    ticker: str
    name: str
    description: str | None
    sector: str | None
    industry: str | None
    headquarters: str | None
    founded_year: int | None
    employees: int | None
    website: str | None
    is_active: bool
    tags: list[CompanyTagResponse]
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    total: int
