"""Dashboard API routes — aggregated daily workspace data."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("")
async def get_dashboard(container: Container = Depends(get_container)):
    """Full dashboard data — brief, market overview, watchlist, reminders, research."""
    svc = container.dashboard_service
    data = await svc.get_dashboard()
    data["market_overview"] = await svc.get_market_overview()
    return data


@router.get("/brief")
async def get_latest_brief(container: Container = Depends(get_container)):
    """Latest morning brief only."""
    svc = container.dashboard_service
    brief = await svc.get_latest_brief()
    return {"brief": brief}


@router.get("/watchlist")
async def get_watchlist_summary(container: Container = Depends(get_container)):
    """Watchlist summary with enriched data."""
    svc = container.dashboard_service
    return {"watchlist": await svc.get_watchlist_summary()}


@router.post("/generate-brief")
async def generate_brief():
    """Manually trigger morning brief generation via scheduler."""
    from core.scheduler import run_job_now

    result = await run_job_now("morning_brief")
    return {"status": "ok", "result": result}
