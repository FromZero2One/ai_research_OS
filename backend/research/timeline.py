"""Research Timeline — cross-session research history + report diff."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from research.timeline_service import TimelineService

router = APIRouter(tags=["Research Timeline"])


@router.get("/timeline")
async def get_research_timeline(
    ticker: str = Query(..., description="Company ticker"),
    db: AsyncSession = Depends(get_db),
):
    """Get full research timeline for a company.

    Aggregates all sessions, reports, and events into chronological order.
    """
    svc = TimelineService(db)
    return await svc.get_company_timeline(ticker)


@router.get("/reports/{report_id}/diff")
async def get_report_diff(
    report_id: uuid.UUID,
    other_version: int = Query(..., ge=1, description="Version to compare against"),
    db: AsyncSession = Depends(get_db),
):
    """Compare two versions of a report and return structured diff."""
    svc = TimelineService(db)
    return await svc.get_report_diff(report_id, other_version)


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get timeline for a single research session."""
    svc = TimelineService(db)
    return await svc.get_session_timeline(session_id)
