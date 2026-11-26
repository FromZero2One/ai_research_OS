"""Scheduler API routes — status check, manual job trigger."""

from __future__ import annotations

from fastapi import APIRouter

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
