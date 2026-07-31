"""Search endpoints — stock search by code/name and symbol listing."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/market", tags=["Market Center"])


@router.get("/search")
async def search_stocks(
    query: str = Query(..., min_length=1, description="股票代码或名称"),
    limit: int = Query(20, le=100),
    container: Container = Depends(get_container),
):
    """Search stocks by code or Chinese name."""
    svc = container.search_service
    results = await svc.search_stocks(query, limit)
    return {"query": query, "count": len(results), "results": results}


@router.get("/symbols")
async def list_symbols(
    limit: int = Query(100, le=500),
    container: Container = Depends(get_container),
):
    """List all A-stocks with available K-line data."""
    svc = container.search_service
    symbols = await svc.list_available_symbols(limit)
    return {"count": len(symbols), "symbols": symbols}
