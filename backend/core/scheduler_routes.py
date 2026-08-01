"""Scheduler API routes — status check, manual job trigger, observations, tasks."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query

from core.observation_engine import get_recent_observations, run_observation_cycle
from core.scheduler import get_scheduler_status, run_job_now
from core.task_manager import list_tasks, retry_task

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


# ── Background Tasks ───────────────────────────────────────────────────


@router.get("/tasks")
async def get_tasks(
    task_type: str | None = None,
    status: str | None = None,
    limit: int = Query(50, le=200),
):
    """List background tasks."""
    tasks = await list_tasks(task_type=task_type, status=status, limit=limit)
    return {
        "tasks": [
            {
                "id": str(t.id),
                "task_type": t.task_type,
                "task_key": t.task_key,
                "status": t.status,
                "attempts": t.attempts,
                "max_attempts": t.max_attempts,
                "error": t.error,
                "created_at": t.created_at.isoformat() if t.created_at else None,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            }
            for t in tasks
        ]
    }


@router.post("/tasks/{task_id}/retry")
async def retry_background_task(task_id: UUID):
    """Reset a failed task so the worker retries it."""
    from core.database import async_session_factory

    async with async_session_factory() as db:
        task = await retry_task(task_id, db)
        if task:
            return {"status": "retrying", "task_id": str(task.id)}
        return {"status": "not_found", "task_id": str(task_id)}
