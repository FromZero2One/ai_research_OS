"""Profile endpoints — stock info and company profile."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/market", tags=["Market Center"])


@router.post("/profile/{ticker}/ingest", status_code=201)
async def ingest_company_profile(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Fetch company profile and update Company record."""
    svc = container.profile_service
    profile = await svc.fetch_and_store_company_profile(ticker)
    return {"ticker": ticker.upper(), "updated": profile}


@router.get("/info/{ticker}")
async def stock_info(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Get A-stock basic info + latest price + valuation snapshot."""
    svc = container.profile_service
    info = await svc.get_stock_info(ticker)
    if info is None:
        return {"ticker": ticker, "error": "Not available or not an A-stock"}
    return info


@router.get("/stock-profile/{ticker}")
async def stock_profile(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Get stock name, sector, and kline status — for mcp-company integration."""
    svc = container.profile_service
    profile = await svc.get_stock_profile(ticker)
    if profile is None:
        return {"symbol": ticker, "error": "Not available or not an A-stock"}
    return profile
