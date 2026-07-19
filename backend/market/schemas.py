"""Market Center Pydantic schemas."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class StockPriceResponse(BaseModel):
    id: UUID
    ticker: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    adjusted_close: float | None

    model_config = {"from_attributes": True}


class StockPriceBatch(BaseModel):
    ticker: str
    prices: list[dict]


class FinancialMetricResponse(BaseModel):
    ticker: str
    fiscal_year: int
    fiscal_period: str
    metric_name: str
    metric_value: float | None

    model_config = {"from_attributes": True}


class PriceQueryParams(BaseModel):
    ticker: str
    start_date: date | None = None
    end_date: date | None = None
    limit: int = Field(default=100, le=1000)
