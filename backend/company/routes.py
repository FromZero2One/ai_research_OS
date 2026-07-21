"""Company Center API routes — includes thesis + workspace endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from company.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
)
from company.service import CompanyService
from core.database import get_db
from core.exceptions import NotFoundError

router = APIRouter(prefix="/companies", tags=["Company Center"])


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    data: CompanyCreate,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    svc = CompanyService(db)
    company = await svc.create(**data.model_dump())
    return CompanyResponse.model_validate(company)


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    query: str | None = Query(None, description="Search by name or ticker"),
    sector: str | None = None,
    industry: str | None = None,
    tag: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> CompanyListResponse:
    svc = CompanyService(db)
    companies, total = await svc.search(
        query=query, sector=sector, industry=industry,
        tag=tag, skip=skip, limit=limit,
    )
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    svc = CompanyService(db)
    company = await svc.get(company_id)
    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    svc = CompanyService(db)
    company = await svc.update(company_id, data.model_dump(exclude_unset=True))
    return CompanyResponse.model_validate(company)


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = CompanyService(db)
    await svc.delete(company_id)


# ── Thesis Panel ──────────────────────────────────────────────────────


class ThesisResponse(BaseModel):
    ticker: str
    company_name: str
    thesis: str | None = None
    decision: str | None = None
    confidence: float | None = None
    source_session_id: str | None = None
    updated_at: str | None = None


class ThesisUpdate(BaseModel):
    thesis: str = Field(..., min_length=10)
    decision: str | None = Field(None, pattern="^(buy|sell|hold|watch|pass)$")
    confidence: float | None = Field(None, ge=0.0, le=1.0)


async def _get_company_by_ticker(ticker: str, db: AsyncSession):
    """Resolve ticker to company."""
    from company.models import Company
    result = await db.execute(
        select(Company).where(Company.ticker == ticker.upper()).limit(1)
    )
    return result.scalar_one_or_none()


@router.get("/by-ticker/{ticker}/thesis", response_model=ThesisResponse)
async def get_thesis(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Get current thesis for a company (latest completed research or manual update)."""
    from core.event_log import EventLog
    from research.models import ResearchSession

    company = await _get_company_by_ticker(ticker, db)
    if not company:
        raise NotFoundError("Company", ticker.upper())

    # 1. Check for manual thesis override in EventLog
    log_result = await db.execute(
        select(EventLog)
        .where(
            EventLog.source == "company",
            EventLog.event_type == "thesis.updated",
            EventLog.entity_id == ticker.upper(),
        )
        .order_by(desc(EventLog.occurred_at))
        .limit(1)
    )
    thesis_log = log_result.scalar_one_or_none()

    if thesis_log and thesis_log.payload:
        return ThesisResponse(
            ticker=ticker.upper(),
            company_name=company.name,
            thesis=thesis_log.payload.get("thesis"),
            decision=thesis_log.payload.get("decision"),
            confidence=thesis_log.payload.get("confidence"),
            updated_at=thesis_log.occurred_at.isoformat() if thesis_log.occurred_at else None,
        )

    # 2. Fallback to latest completed research
    result = await db.execute(
        select(ResearchSession)
        .where(
            ResearchSession.company_id == company.id,
            ResearchSession.status == "completed",
            ResearchSession.thesis.isnot(None),
        )
        .order_by(desc(ResearchSession.updated_at))
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if session and session.thesis:
        return ThesisResponse(
            ticker=ticker.upper(),
            company_name=company.name,
            thesis=session.thesis,
            decision=session.decision,
            confidence=session.confidence,
            source_session_id=str(session.id),
            updated_at=session.updated_at.isoformat() if session.updated_at else None,
        )

    return ThesisResponse(
        ticker=ticker.upper(),
        company_name=company.name,
    )


@router.post("/by-ticker/{ticker}/thesis", response_model=ThesisResponse)
async def update_thesis(
    ticker: str,
    data: ThesisUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Manually set/update thesis for a company."""
    from core.event_log import EventLog
    from core.event_service import EventLogger

    company = await _get_company_by_ticker(ticker, db)
    if not company:
        raise NotFoundError("Company", ticker.upper())

    logger = EventLogger(db)
    await logger.record(
        source="company",
        event_type="thesis.updated",
        entity_type="company",
        entity_id=ticker.upper(),
        payload=data.model_dump(),
    )
    await db.commit()

    return ThesisResponse(
        ticker=ticker.upper(),
        company_name=company.name,
        thesis=data.thesis,
        decision=data.decision,
        confidence=data.confidence,
        updated_at="now",
    )


@router.get("/by-ticker/{ticker}/workspace")
async def get_company_workspace(
    ticker: str,
    db: AsyncSession = Depends(get_db),
):
    """Aggregated company workspace data — thesis, timeline snippets, evidence."""
    from research.models import ResearchSession, ResearchEvidence

    company = await _get_company_by_ticker(ticker, db)
    if not company:
        raise NotFoundError("Company", ticker.upper())

    # Latest thesis
    thesis_result = await get_thesis(ticker, db)

    # Recent research sessions
    result = await db.execute(
        select(ResearchSession)
        .where(ResearchSession.company_id == company.id)
        .order_by(desc(ResearchSession.created_at))
        .limit(5)
    )
    sessions = list(result.scalars().all())

    # Evidence summary across all sessions for this company
    evidence_counts = {"supporting": 0, "opposing": 0, "neutral": 0}
    for s in sessions:
        ev_result = await db.execute(
            select(ResearchEvidence).where(ResearchEvidence.session_id == s.id)
        )
        for ev in ev_result.scalars().all():
            if ev.evidence_type in evidence_counts:
                evidence_counts[ev.evidence_type] += 1

    return {
        "ticker": ticker.upper(),
        "company_name": company.name,
        "company_id": str(company.id),
        "thesis": thesis_result,
        "recent_research": [
            {
                "id": str(s.id),
                "title": s.title,
                "status": s.status,
                "decision": s.decision,
                "thesis": s.thesis,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in sessions
        ],
        "evidence_summary": evidence_counts,
    }
