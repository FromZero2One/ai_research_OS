"""Dashboard API routes — aggregated daily workspace data."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dashboard.service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("")
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """Full dashboard data — morning brief, market overview, watchlist, reminders, recent research."""
    svc = DashboardService(db)
    data = await svc.get_dashboard()
    data["market_overview"] = await svc.get_market_overview()
    return data


@router.get("/brief")
async def get_latest_brief(db: AsyncSession = Depends(get_db)):
    """Latest morning brief only."""
    svc = DashboardService(db)
    brief = await svc.get_latest_brief()
    return {"brief": brief}


@router.get("/watchlist")
async def get_watchlist_summary(db: AsyncSession = Depends(get_db)):
    """Watchlist summary with enriched data."""
    svc = DashboardService(db)
    return {"watchlist": await svc.get_watchlist_summary()}


@router.post("/generate-brief")
async def generate_brief():
    """Manually trigger morning brief generation via scheduler."""
    from core.scheduler import run_job_now
    result = await run_job_now("morning_brief")
    return {"status": "ok", "result": result}
