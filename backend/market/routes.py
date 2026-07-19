"""Market Center API routes."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from market.schemas import FinancialMetricResponse, StockPriceResponse
from market.service import MarketService

router = APIRouter(prefix="/market", tags=["Market Center"])


@router.get("/prices/{ticker}")
async def get_prices(
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    svc = MarketService(db)
    prices = await svc.get_prices(ticker, start_date, end_date, limit)
    return {"ticker": ticker.upper(), "count": len(prices), "prices": prices}


@router.post("/prices/{ticker}/ingest", status_code=201)
async def ingest_prices(
    ticker: str,
    provider: str = Query("yfinance", pattern="^(yfinance|akshare)$"),
    db: AsyncSession = Depends(get_db),
):
    svc = MarketService(db)
    count = await svc.fetch_and_store_prices(ticker, provider)
    return {"ticker": ticker.upper(), "ingested": count, "provider": provider}


@router.get("/financials/{ticker}")
async def get_financials(
    ticker: str,
    metric: str | None = None,
    fiscal_year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    svc = MarketService(db)
    metrics = await svc.get_financials(ticker, metric, fiscal_year)
    return {"ticker": ticker.upper(), "count": len(metrics), "metrics": metrics}
