"""Scheduled job: event log retention cleanup."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from core.config import settings
from core.database import managed_session
from core.event_log import EventLog
from core.logging import logger


async def event_log_cleanup() -> dict:
    """Delete event log entries older than the retention window.

    The event log is a write-once audit trail and grows unboundedly
    (every search is recorded), so a weekly cleanup keeps it bounded.
    """
    cutoff = datetime.now(UTC) - timedelta(days=settings.EVENT_LOG_RETENTION_DAYS)
    async with managed_session() as session:
        result = await session.execute(delete(EventLog).where(EventLog.occurred_at < cutoff))
        deleted = result.rowcount or 0  # type: ignore[attr-defined]
        await session.commit()
    logger.info("Event log cleanup: deleted %d entries older than %s", deleted, cutoff.date())
    return {"deleted": deleted, "cutoff": cutoff.date().isoformat()}
