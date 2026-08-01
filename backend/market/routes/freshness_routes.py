"""Freshness endpoints — data freshness records and stats."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/market", tags=["Market Center"])


@router.get("/freshness")
async def get_data_freshness(
    ticker: str | None = Query(None, description="Filter by ticker"),
    data_type: str | None = Query(
        None, description="Filter by type: prices|financials|profile|news"
    ),
    status: str | None = Query(None, description="Filter by status: ok|stale|error"),
    limit: int = Query(100, le=500),
    container: Container = Depends(get_container),
):
    """Query data freshness records — when each ticker's data was last fetched."""
    svc = container.freshness_service
    records = await svc.get_freshness(
        ticker=ticker,
        data_type=data_type,
        status=status,
        limit=limit,
    )
    return {"count": len(records), "records": records}


@router.get("/freshness/stats")
async def get_freshness_stats(
    container: Container = Depends(get_container),
):
    """Aggregate freshness stats across all data types."""
    svc = container.freshness_service
    return await svc.get_overall_stats()


@router.get("/freshness/stale")
async def get_stale_data(
    data_type: str | None = None,
    min_age_hours: int | None = None,
    container: Container = Depends(get_container),
):
    """Get all tickers with stale data (exceeds freshness threshold)."""
    svc = container.freshness_service
    stale = await svc.get_stale_tickers(
        data_type=data_type,
        min_age_hours=min_age_hours,
    )
    return {"count": len(stale), "records": stale}


@router.get("/freshness/{ticker}")
async def get_ticker_freshness(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Get freshness summary for a single ticker."""
    svc = container.freshness_service
    summary = await svc.get_ticker_summary(ticker)
    return summary
