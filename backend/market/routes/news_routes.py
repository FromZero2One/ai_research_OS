"""News endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/market", tags=["Market Center"])


@router.get("/news/{ticker}")
async def get_news(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Get news for a stock via 2-layer fallback: local akshare → cloud MCP."""
    svc = container.news_service
    news, source = await svc.fetch_news(ticker)
    return {"ticker": ticker.upper(), "news": news, "source": source}
