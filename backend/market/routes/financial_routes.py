"""Financial endpoints — financial metrics query and ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import Container
from core.database import get_container
from market.akshare_executor import is_a_stock

router = APIRouter(prefix="/market", tags=["Market Center"])


@router.get("/financials/{ticker}")
async def get_financials(
    ticker: str,
    metric: str | None = None,
    fiscal_year: int | None = None,
    container: Container = Depends(get_container),
):
    """Get financial metrics. A-stocks → akshare MySQL; HK stocks → eastmoney HK API."""
    svc = container.financial_service
    metrics = await svc.get_financials(ticker, metric, fiscal_year)
    return {
        "ticker": ticker.upper(),
        "count": len(metrics),
        "metrics": [m.as_dict() for m in metrics],
    }


@router.post("/financials/{ticker}/ingest", status_code=201)
async def ingest_financials(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Ingest financial metrics (HK stocks via eastmoney HK API)."""
    if is_a_stock(ticker):
        return {
            "ticker": ticker.upper(),
            "ingested": 0,
            "source": "mysql",
            "note": "A-stock financials served from MySQL — no ingest needed",
        }

    svc = container.financial_service
    fetched = await svc._fetch_akshare_financials(ticker)
    count = await svc.upsert_financials(ticker, fetched)
    return {"ticker": ticker.upper(), "ingested": count, "source": "akshare_hk"}
