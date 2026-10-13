"""Search endpoints — stock search by code/name (PG Companies table)."""

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
    """Search companies by code or Chinese name."""
    svc = container.search_service
    results = await svc.search_stocks(query, limit)
    return {"query": query, "count": len(results), "results": results}
