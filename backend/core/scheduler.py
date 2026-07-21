"""APScheduler-based task scheduler — daily market data, morning brief, etc.

Wired into api/app.py lifespan: starts on boot, shuts down gracefully.
Jobs are registered from settings; each logs its execution via EventLogger.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import settings
from core.logging import logger

# ── Job registry ────────────────────────────────────────────────────

_jobs: dict[str, Callable[[], Awaitable[Any]]] = {}
_scheduler: AsyncIOScheduler | None = None


def register_job(name: str, func: Callable[[], Awaitable[Any]]) -> None:
    """Register an async job function by name."""
    _jobs[name] = func
    logger.debug("Scheduler job registered: %s", name)


async def run_job(name: str) -> dict[str, Any]:
    """Execute a registered job by name, returning its result."""
    func = _jobs.get(name)
    if not func:
        logger.warning("Scheduler job not found: %s", name)
        return {"status": "error", "message": f"Job '{name}' not found"}
    try:
        logger.info("Scheduler job starting: %s", name)
        result = await func()
        logger.info("Scheduler job completed: %s", name)
        return {"status": "ok", "job": name, "result": result}
    except Exception as e:
        logger.error("Scheduler job failed: %s — %s", name, e)
        return {"status": "error", "job": name, "message": str(e)}


async def run_job_now(name: str) -> dict[str, Any]:
    """Run a job immediately (triggered via API)."""
    return await run_job(name)


def start_scheduler() -> AsyncIOScheduler:
    """Create and start the scheduler, registering configured jobs."""
    global _scheduler
    if _scheduler and _scheduler.running:
        logger.warning("Scheduler already running")
        return _scheduler

    _scheduler = AsyncIOScheduler()
    _scheduler._logger = logger  # Use our logger

    # Register market data update job (Weekdays 2am)
    if hasattr(settings, "MARKET_DATA_SCHEDULE") and settings.MARKET_DATA_SCHEDULE:
        _add_cron_job(
            "market_data_update",
            settings.MARKET_DATA_SCHEDULE,
        )

    # Register morning brief job (Weekdays 6am)
    if hasattr(settings, "REPORT_SCHEDULE") and settings.REPORT_SCHEDULE:
        _add_cron_job(
            "morning_brief",
            settings.REPORT_SCHEDULE,
        )

    # Register observation cycle job (before morning brief)
    if hasattr(settings, "OBSERVATION_SCHEDULE") and settings.OBSERVATION_SCHEDULE:
        _add_cron_job(
            "observation_cycle",
            settings.OBSERVATION_SCHEDULE,
        )

    if _scheduler.get_jobs():
        _scheduler.start()
        logger.info(
            "Scheduler started with %d job(s)", len(_scheduler.get_jobs())
        )
    else:
        logger.info("Scheduler started — no jobs configured")

    return _scheduler


def _add_cron_job(job_name: str, cron_expr: str) -> None:
    """Add a cron job to the scheduler."""
    if job_name not in _jobs:
        logger.debug("Skipping job %s (not registered)", job_name)
        return

    parts = cron_expr.strip().split()
    if len(parts) != 5:
        logger.warning("Invalid cron expression for %s: %s", job_name, cron_expr)
        return

    _scheduler.add_job(  # type: ignore[union-attr]
        _run_async_job_wrapper(job_name),
        trigger=CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4],
            timezone="Asia/Shanghai",
        ),
        id=job_name,
        name=job_name,
        replace_existing=True,
    )
    logger.info(
        "Scheduled job '%s' at cron '%s'", job_name, cron_expr
    )


def _run_async_job_wrapper(job_name: str) -> Callable[[], Awaitable[None]]:
    """Wrap a registered job for APScheduler (handles errors gracefully)."""

    async def wrapper() -> None:
        await run_job(job_name)

    return wrapper


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")
    _scheduler = None


def get_scheduler_status() -> dict:
    """Return scheduler status for health/API endpoints."""
    if _scheduler and _scheduler.running:
        jobs = _scheduler.get_jobs()
        return {
            "running": True,
            "jobs": [
                {
                    "id": j.id,
                    "next_run": str(j.next_run_time) if j.next_run_time else None,
                    "trigger": str(j.trigger),
                }
                for j in jobs
            ],
        }
    return {"running": False, "jobs": []}
