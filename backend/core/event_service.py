"""Service for writing event log entries."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from core.event_log import EventLog


class EventLogger:
    """Thin write-only service for recording research events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self,
        source: str,
        event_type: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        actor: str | None = None,
        payload: dict | None = None,
        summary: str | None = None,
    ) -> EventLog:
        entry = EventLog(
            source=source,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
            payload=payload,
            summary=summary,
            occurred_at=datetime.now(timezone.utc),
        )
        self.session.add(entry)
        return entry
