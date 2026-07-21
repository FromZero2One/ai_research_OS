"""Scheduler API routes — status check, manual job trigger, observations."""

from __future__ import annotations

from fastapi import APIRouter, Query

from core.observation_engine import get_recent_observations, run_observation_cycle
from core.scheduler import get_scheduler_status, run_job_now

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


@router.get("/status")
async def scheduler_status():
    """Get scheduler status and registered jobs."""
    return get_scheduler_status()


@router.post("/run/{job_name}")
async def trigger_job(job_name: str):
    """Manually trigger a scheduled job by name."""
    result = await run_job_now(job_name)
    return result


# ── Observation Engine ────────────────────────────────────────────────


@router.post("/observe")
async def trigger_observation():
    """Manually trigger observation cycle."""
    result = await run_observation_cycle()
    return {"observation": result}


@router.get("/observations")
async def list_observations(limit: int = Query(20, le=100)):
    """List recent observations from the observation engine."""
    observations = await get_recent_observations(limit=limit)
    return {"observations": observations}
