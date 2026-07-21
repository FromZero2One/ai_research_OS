"""Research Timeline — cross-session research history + report diff."""

from __future__ import annotations

import difflib
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.exceptions import NotFoundError
from research.models import ResearchReport, ResearchSession

router = APIRouter(prefix="/research", tags=["Research Timeline"])


# ── Timeline ──────────────────────────────────────────────────────────


async def _get_company_by_ticker(ticker: str, db: AsyncSession) -> tuple[uuid.UUID | None, str | None]:
    """Resolve ticker to company_id and name."""
    from company.models import Company
    result = await db.execute(
        select(Company).where(Company.ticker == ticker.upper()).limit(1)
    )
    company = result.scalar_one_or_none()
    if not company:
        return None, None
    return company.id, company.name


@router.get("/timeline")
async def get_research_timeline(
    ticker: str = Query(..., description="Company ticker"),
    db: AsyncSession = Depends(get_db),
):
    """Get full research timeline for a company.

    Aggregates all sessions, reports, and events into chronological order.
    """
    from core.event_log import EventLog

    company_id, company_name = await _get_company_by_ticker(ticker, db)
    if not company_id:
        return {"ticker": ticker.upper(), "company_name": None, "events": []}

    # 1. All sessions for this company
    result = await db.execute(
        select(ResearchSession)
        .where(ResearchSession.company_id == company_id)
        .options(
            selectinload(ResearchSession.reports),
            selectinload(ResearchSession.evidences),
        )
        .order_by(ResearchSession.created_at.asc())
    )
    sessions = list(result.scalars().all())

    # 2. Build flat event list
    events: list[dict[str, Any]] = []

    for s in sessions:
        # Session created
        events.append({
            "type": "session_created",
            "date": s.created_at.isoformat() if s.created_at else "",
            "session_id": str(s.id),
            "session_title": s.title,
            "detail": "创建研究",
            "status": s.status,
        })

        # Status changes from EventLog
        log_result = await db.execute(
            select(EventLog)
            .where(
                EventLog.entity_id == str(s.id),
                EventLog.source == "research",
            )
            .order_by(EventLog.occurred_at.asc())
        )
        log_entries = list(log_result.scalars().all())

        for log in log_entries:
            event_type = log.event_type
            # Map event types to display
            if event_type == "research.plan_generated":
                events.append({
                    "type": "plan_generated",
                    "date": log.occurred_at.isoformat() if log.occurred_at else "",
                    "session_id": str(s.id),
                    "session_title": s.title,
                    "detail": "AI 研究计划生成",
                })
            elif event_type == "evidence.added":
                # Skip individual evidence events to avoid noise
                pass
            elif event_type == "report.created" or event_type == "report.generated":
                events.append({
                    "type": "report_generated",
                    "date": log.occurred_at.isoformat() if log.occurred_at else "",
                    "session_id": str(s.id),
                    "session_title": s.title,
                    "detail": "研究报告生成",
                })
            elif event_type == "research.completed":
                events.append({
                    "type": "research_completed",
                    "date": log.occurred_at.isoformat() if log.occurred_at else "",
                    "session_id": str(s.id),
                    "session_title": s.title,
                    "thesis": s.thesis,
                    "decision": s.decision,
                    "confidence": s.confidence,
                    "detail": f"研究完结 - {s.decision}" if s.decision else "研究完结",
                })
            elif event_type.startswith("research."):
                status_name = event_type.replace("research.", "")
                events.append({
                    "type": "status_change",
                    "date": log.occurred_at.isoformat() if log.occurred_at else "",
                    "session_id": str(s.id),
                    "session_title": s.title,
                    "detail": f"状态变更: {status_name}",
                })

        # Report versions
        for report in (s.reports or []):
            events.append({
                "type": "report_version",
                "date": report.created_at.isoformat() if report.created_at else "",
                "session_id": str(s.id),
                "session_title": s.title,
                "report_id": str(report.id),
                "version": report.version,
                "is_final": report.is_final,
                "detail": f"报告 v{report.version}{' (终稿)' if report.is_final else ''}",
            })

    # Sort by date ascending
    events.sort(key=lambda e: e.get("date", ""))

    return {
        "ticker": ticker.upper(),
        "company_name": company_name,
        "events": events,
    }


# ── Report Diff ───────────────────────────────────────────────────────


@router.get("/reports/{report_id}/diff")
async def get_report_diff(
    report_id: uuid.UUID,
    other_version: int = Query(..., ge=1, description="Version to compare against"),
    db: AsyncSession = Depends(get_db),
):
    """Compare two versions of a report and return structured diff."""
    # Get the current report
    result = await db.execute(
        select(ResearchReport).where(ResearchReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise NotFoundError("ResearchReport", str(report_id))

    # Get the other version
    result = await db.execute(
        select(ResearchReport)
        .where(
            ResearchReport.session_id == report.session_id,
            ResearchReport.version == other_version,
        )
    )
    other = result.scalar_one_or_none()
    if not other:
        raise NotFoundError("ResearchReport", f"version {other_version}")

    # Generate diff
    old_lines = other.content.splitlines(keepends=True)
    new_lines = report.content.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"v{other_version}",
        tofile=f"v{report.version}",
        n=3,
    ))

    # Parse diff into structured format
    additions = 0
    deletions = 0
    for line in diff:
        if line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return {
        "report_id": str(report.id),
        "session_id": str(report.session_id),
        "from_version": other_version,
        "to_version": report.version,
        "diff": "".join(diff),
        "stats": {
            "additions": additions,
            "deletions": deletions,
            "context_lines": len(diff) - additions - deletions - 2,  # -2 for file headers
        },
    }


# ─── Session Timeline (within one session) ────────────────────────────


@router.get("/sessions/{session_id}/timeline")
async def get_session_timeline(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get timeline for a single research session."""
    from core.event_log import EventLog

    result = await db.execute(
        select(ResearchSession)
        .where(ResearchSession.id == session_id)
        .options(
            selectinload(ResearchSession.reports).order_by(ResearchReport.version),
            selectinload(ResearchSession.evidences),
        )
    )
    session = result.scalar_one_or_none()
    if not session:
        raise NotFoundError("ResearchSession", str(session_id))

    events: list[dict[str, Any]] = []

    # Session created
    events.append({
        "type": "created",
        "date": session.created_at.isoformat() if session.created_at else "",
        "detail": "研究会话创建",
    })

    # Event log entries
    log_result = await db.execute(
        select(EventLog)
        .where(
            EventLog.entity_id == str(session_id),
            EventLog.source == "research",
        )
        .order_by(EventLog.occurred_at.asc())
    )
    for log in log_result.scalars().all():
        event_type = log.event_type.replace("research.", "")
        if event_type == "evidence.added":
            continue  # skip noise
        events.append({
            "type": event_type,
            "date": log.occurred_at.isoformat() if log.occurred_at else "",
            "detail": log.summary or event_type,
        })

    # Report versions
    for report in (session.reports or []):
        events.append({
            "type": "report_version",
            "date": report.created_at.isoformat() if report.created_at else "",
            "version": report.version,
            "is_final": report.is_final,
            "report_id": str(report.id),
            "detail": f"报告 v{report.version}{' (终稿)' if report.is_final else ''}",
        })

    # Sort by date
    events.sort(key=lambda e: e.get("date", ""))

    return {
        "session_id": str(session_id),
        "session_title": session.title,
        "status": session.status,
        "thesis": session.thesis,
        "decision": session.decision,
        "events": events,
    }
