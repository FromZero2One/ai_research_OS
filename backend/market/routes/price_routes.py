"""Price endpoints — price history and ingestion."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/market", tags=["Market Center"])


@router.get("/prices/{ticker}")
async def get_prices(
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, le=1000),
    container: Container = Depends(get_container),
):
    """Get stock price history. A-stocks → akshare MySQL; US stocks → PostgreSQL."""
    svc = container.price_service
    prices = await svc.get_prices(ticker, start_date, end_date, limit)
    return {
        "ticker": ticker.upper(),
        "count": len(prices),
        "prices": [p.as_dict() for p in prices],
        "source": "postgresql",
    }


@router.post("/prices/{ticker}/ingest", status_code=201)
async def ingest_prices(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Ingest prices via akshare 3-layer chain (MySQL → local → cloud)."""
    svc = container.price_service
    count, warnings = await svc.fetch_and_store_prices(ticker)
    result = {"ticker": ticker.upper(), "ingested": count}
    if warnings:
        result["warnings"] = warnings
    return result
