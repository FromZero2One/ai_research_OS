"""Market Center API routes — each endpoint uses the appropriate service."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from market.financial_service import FinancialService
from market.freshness_service import FreshnessService
from market.news_service import NewsService
from market.price_service import PriceService
from market.profile_service import ProfileService
from market.search_service import SearchService

router = APIRouter(prefix="/market", tags=["Market Center"])


# ── Prices ─────────────────────────────────────────────────────────────


@router.get("/prices/{ticker}")
async def get_prices(
    ticker: str,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """Get stock price history. A-stocks → akshare MySQL; US stocks → PostgreSQL."""
    svc = PriceService(db)
    prices = await svc.get_prices(ticker, start_date, end_date, limit)
    return {"ticker": ticker.upper(), "count": len(prices), "prices": prices, "source": "postgresql"}


@router.post("/prices/{ticker}/ingest", status_code=201)
async def ingest_prices(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Ingest prices via akshare 3-layer chain (MySQL → local → cloud)."""
    svc = PriceService(db)
    count, warnings = await svc.fetch_and_store_prices(ticker)
    result = {"ticker": ticker.upper(), "ingested": count}
    if warnings:
        result["warnings"] = warnings
    return result


# ── Financials ─────────────────────────────────────────────────────────


@router.get("/financials/{ticker}")
async def get_financials(
    ticker: str,
    metric: str | None = None,
    fiscal_year: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get financial metrics. A-stocks → akshare MySQL; HK stocks → eastmoney HK API."""
    svc = FinancialService(db)
    metrics = await svc.get_financials(ticker, metric, fiscal_year)
    return {"ticker": ticker.upper(), "count": len(metrics), "metrics": metrics}


@router.post("/financials/{ticker}/ingest", status_code=201)
async def ingest_financials(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Ingest financial metrics (HK stocks via eastmoney HK API)."""
    from market.akshare_executor import is_a_stock
    if is_a_stock(ticker):
        return {"ticker": ticker.upper(), "ingested": 0, "source": "mysql",
                "note": "A-stock financials served from MySQL — no ingest needed"}

    svc = FinancialService(db)
    from market.models import FinancialMetric
    fetched = await svc._fetch_akshare_financials(ticker)
    count = await svc.upsert_financials(ticker, fetched)
    return {"ticker": ticker.upper(), "ingested": count, "source": "akshare_hk"}


# ── Company Profile ────────────────────────────────────────────────────


@router.post("/profile/{ticker}/ingest", status_code=201)
async def ingest_company_profile(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Fetch company profile and update Company record."""
    svc = ProfileService(db)
    profile = await svc.fetch_and_store_company_profile(ticker)
    return {"ticker": ticker.upper(), "updated": profile}


# ── News ───────────────────────────────────────────────────────────────


@router.get("/news/{ticker}")
async def get_news(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get news for a stock via 2-layer fallback: local akshare → cloud MCP."""
    svc = NewsService(db)
    news, source = await svc.fetch_news(ticker)
    return {"ticker": ticker.upper(), "news": news, "source": source}


# ── Search ─────────────────────────────────────────────────────────────


@router.get("/search")
async def search_stocks(
    query: str = Query(..., min_length=1, description="股票代码或名称"),
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search stocks by code or Chinese name."""
    svc = SearchService(db)
    results = await svc.search_stocks(query, limit)
    return {"query": query, "count": len(results), "results": results}


@router.get("/symbols")
async def list_symbols(
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """List all A-stocks with available K-line data."""
    svc = SearchService(db)
    symbols = await svc.list_available_symbols(limit)
    return {"count": len(symbols), "symbols": symbols}


# ── Stock Info / Profile ───────────────────────────────────────────────


@router.get("/info/{ticker}")
async def stock_info(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get A-stock basic info + latest price + valuation snapshot."""
    svc = ProfileService(db)
    info = await svc.get_stock_info(ticker)
    if info is None:
        return {"ticker": ticker, "error": "Not available or not an A-stock"}
    return info


@router.get("/stock-profile/{ticker}")
async def stock_profile(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get stock name, sector, and kline status — for mcp-company integration."""
    svc = ProfileService(db)
    profile = await svc.get_stock_profile(ticker)
    if profile is None:
        return {"symbol": ticker, "error": "Not available or not an A-stock"}
    return profile


# ── Data Freshness ────────────────────────────────────────────────────


@router.get("/freshness")
async def get_data_freshness(
    ticker: str | None = Query(None, description="Filter by ticker"),
    data_type: str | None = Query(None, description="Filter by type: prices|financials|profile|news"),
    status: str | None = Query(None, description="Filter by status: ok|stale|error"),
    limit: int = Query(100, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Query data freshness records — when each ticker's data was last fetched."""
    svc = FreshnessService(db)
    records = await svc.get_freshness(
        ticker=ticker, data_type=data_type, status=status, limit=limit,
    )
    return {"count": len(records), "records": records}


@router.get("/freshness/stats")
async def get_freshness_stats(
    db: AsyncSession = Depends(get_db),
):
    """Aggregate freshness stats across all data types."""
    svc = FreshnessService(db)
    stats = await svc.get_overall_stats()
    return stats


@router.get("/freshness/stale")
async def get_stale_data(
    data_type: str | None = None,
    min_age_hours: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Get all tickers with stale data (exceeds freshness threshold)."""
    svc = FreshnessService(db)
    stale = await svc.get_stale_tickers(
        data_type=data_type, min_age_hours=min_age_hours,
    )
    return {"count": len(stale), "records": stale}


@router.get("/freshness/{ticker}")
async def get_ticker_freshness(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get freshness summary for a single ticker."""
    svc = FreshnessService(db)
    summary = await svc.get_ticker_summary(ticker)
    return summary
