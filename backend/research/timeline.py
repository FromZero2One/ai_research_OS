"""Research Timeline — cross-session research history + report diff."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from core.container import Container
from core.database import get_container

router = APIRouter(tags=["Research Timeline"])


@router.get("/timeline")
async def get_research_timeline(
    ticker: str = Query(..., description="Company ticker"),
    container: Container = Depends(get_container),
):
    """Get full research timeline for a company.

    Aggregates all sessions, reports, and events into chronological order.
    """
    svc = container.timeline_service
    return await svc.get_company_timeline(ticker)


@router.get("/reports/{report_id}/diff")
async def get_report_diff(
    report_id: uuid.UUID,
    other_version: int = Query(..., ge=1, description="Version to compare against"),
    container: Container = Depends(get_container),
):
    """Compare two versions of a report and return structured diff."""
    svc = container.timeline_service
    return await svc.get_report_diff(report_id, other_version)


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(
    session_id: uuid.UUID,
    container: Container = Depends(get_container),
):
    """Get timeline for a single research session."""
    svc = container.timeline_service
    return await svc.get_session_timeline(session_id)


@router.get("/sessions/{session_id}/evolution")
async def get_evolution_summary(
    session_id: uuid.UUID,
    container: Container = Depends(get_container),
):
    """LLM 总结该公司历次研究的论点演变（论点演变/已证伪判断/新增信息/结论漂移）。

    LLM 失败时降级为机械的历史论点摘要，不阻塞页面。
    """
    svc = container.timeline_service
    return await svc.get_evolution_summary(session_id)
