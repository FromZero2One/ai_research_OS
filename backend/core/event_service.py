"""Service for writing event log entries (audit trail, write-only usage)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.event_log import EventLog


class EventLogger:
    """Event log service — write audit trail (查询 API 已随事件路由退役删除)."""

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

