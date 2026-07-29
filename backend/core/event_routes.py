"""Event Log API — read/query the audit trail."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.event_service import EventLogger

router = APIRouter(prefix="/events", tags=["Event Log"])


@router.get("")
async def list_events(
    source: str | None = Query(None, description="Filter by source (e.g. company, research, observation)"),
    event_type: str | None = Query(None, description="Filter by event type (e.g. company.created, research.started)"),
    entity_id: str | None = Query(None, description="Filter by entity ID"),
    entity_type: str | None = Query(None, description="Filter by entity type"),
    since: datetime | None = Query(None, description="ISO datetime (inclusive)"),
    until: datetime | None = Query(None, description="ISO datetime (inclusive)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Query event log entries with filters. Returns paginated results."""
    svc = EventLogger(db)
    entries, total = await svc.list(
        source=source,
        event_type=event_type,
        entity_id=entity_id,
        entity_type=entity_type,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "entries": [EventLogger.to_dict(e) for e in entries],
    }


@router.get("/latest")
async def get_latest_events(
    source: str | None = None,
    event_type: str | None = None,
    entity_id: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get the most recent event log entries."""
    svc = EventLogger(db)
    entries = await svc.get_latest(
        source=source,
        event_type=event_type,
        entity_id=entity_id,
        limit=limit,
    )
    return {
        "entries": [EventLogger.to_dict(e) for e in entries],
    }


@router.get("/sources")
async def list_event_sources(
    db: AsyncSession = Depends(get_db),
):
    """List distinct event sources."""
    svc = EventLogger(db)
    sources = await svc.get_sources()
    return {"sources": sources}


@router.get("/stats")
async def event_stats(
    db: AsyncSession = Depends(get_db),
):
    """Event counts grouped by source."""
    svc = EventLogger(db)
    counts = await svc.count_by_source()
    return {"counts": counts}
