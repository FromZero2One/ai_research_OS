"""Service for reading and writing event log entries."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_log import EventLog


class EventLogger:
    """Event log service — write audit trail + read/query capability."""

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
            occurred_at=datetime.now(UTC),
        )
        self.session.add(entry)
        return entry

    # ── Read / Query ─────────────────────────────────────────────────────

    async def list_events(
        self,
        source: str | None = None,
        event_type: str | None = None,
        entity_id: str | None = None,
        entity_type: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[EventLog], int]:
        """Query event log entries with optional filters, returns (entries, total)."""
        stmt = select(EventLog)

        if source:
            stmt = stmt.where(EventLog.source == source)
        if event_type:
            stmt = stmt.where(EventLog.event_type == event_type)
        if entity_id:
            stmt = stmt.where(EventLog.entity_id == entity_id)
        if entity_type:
            stmt = stmt.where(EventLog.entity_type == entity_type)
        if since:
            stmt = stmt.where(EventLog.occurred_at >= since)
        if until:
            stmt = stmt.where(EventLog.occurred_at <= until)

        # Count
        count_stmt = stmt.with_only_columns(func.count(EventLog.id)).order_by(None)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        # Fetch
        stmt = stmt.order_by(desc(EventLog.occurred_at)).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        entries = list(result.scalars().all())

        return entries, total

    async def get_latest(
        self,
        source: str | None = None,
        event_type: str | None = None,
        entity_id: str | None = None,
        limit: int = 10,
    ) -> list[EventLog]:
        """Get most recent event log entries."""
        stmt = select(EventLog)
        if source:
            stmt = stmt.where(EventLog.source == source)
        if event_type:
            stmt = stmt.where(EventLog.event_type == event_type)
        if entity_id:
            stmt = stmt.where(EventLog.entity_id == entity_id)
        stmt = stmt.order_by(desc(EventLog.occurred_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_source(self) -> list[dict]:
        """Count events grouped by source."""
        from sqlalchemy import func

        stmt = (
            select(EventLog.source, func.count(EventLog.id).label("count"))
            .group_by(EventLog.source)
            .order_by(desc("count"))
        )
        result = await self.session.execute(stmt)
        return [{"source": row[0], "count": row[1]} for row in result.all()]

    async def get_sources(self) -> list[str]:
        """List distinct event sources."""
        stmt = select(EventLog.source).distinct().order_by(EventLog.source)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    def to_dict(entry: EventLog) -> dict:
        """Serialize an EventLog entry to a dict."""
        return {
            "id": str(entry.id),
            "source": entry.source,
            "event_type": entry.event_type,
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "actor": entry.actor,
            "payload": entry.payload,
            "summary": entry.summary,
            "occurred_at": entry.occurred_at.isoformat() if entry.occurred_at else None,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
