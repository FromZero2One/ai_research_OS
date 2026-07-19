"""Market Center API routes — data sourced from akshare MySQL (A-stocks)."""

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
    """Get stock price history.

    A-stocks (digit symbols) → akshare MySQL (腾讯数据源，无需代理)
    US stocks (letter symbols) → PostgreSQL (需预先通过 yfinance 采集)
    """
    svc = MarketService(db)
    prices = await svc.get_prices(ticker, start_date, end_date, limit)
    return {"ticker": ticker.upper(), "count": len(prices), "prices": prices}


@router.post("/prices/{ticker}/ingest", status_code=201)
async def ingest_prices(
    ticker: str,
    provider: str = Query("yfinance", pattern="^(yfinance|akshare)$"),
    db: AsyncSession = Depends(get_db),
):
    """Ingest prices from yfinance/AKShare into PostgreSQL.

    Note: A-stocks now use MySQL adapter directly. This endpoint is
    mainly for US stocks or explicit data fetching.
    """
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
    """Get financial metrics.

    A-stocks → akshare MySQL (EPS, revenue, ROE, etc.)
    """
    svc = MarketService(db)
    metrics = await svc.get_financials(ticker, metric, fiscal_year)
    return {"ticker": ticker.upper(), "count": len(metrics), "metrics": metrics}


@router.get("/search")
async def search_stocks(
    query: str = Query(..., min_length=1, description="股票代码或名称"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search A-stocks by symbol or Chinese name.

    示例: /api/v1/market/search?query=茅台
          /api/v1/market/search?query=600519
    """
    svc = MarketService(db)
    results = await svc.search_stocks(query, limit)
    return {"query": query, "count": len(results), "results": results}


@router.get("/info/{ticker}")
async def stock_info(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get A-stock basic info + latest price + valuation snapshot.

    示例: /api/v1/market/info/600519
    """
    svc = MarketService(db)
    info = await svc.get_stock_info(ticker)
    if info is None:
        return {"ticker": ticker, "error": "Not available or not an A-stock"}
    return info


@router.get("/symbols")
async def list_symbols(
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List all A-stocks with available K-line data."""
    svc = MarketService(db)
    symbols = await svc.list_available_symbols(limit)
    return {"count": len(symbols), "symbols": symbols}
