"""Research Center API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from research.schemas import (
    EvidenceCreate,
    EvidenceResponse,
    ReportResponse,
    ResearchSessionCreate,
    ResearchSessionDetail,
    ResearchSessionResponse,
    ResearchSessionUpdate,
)
from research.service import ResearchService

router = APIRouter(prefix="/research", tags=["Research Center"])


# ── Sessions ────────────────────────────────────────────────────────

@router.post("/sessions", response_model=ResearchSessionResponse, status_code=201)
async def create_session(
    data: ResearchSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    session = await svc.create_session(**data.model_dump())
    return session


@router.get("/sessions", response_model=list[ResearchSessionResponse])
async def list_sessions(
    status: str | None = Query(None, pattern="^(draft|researching|reviewing|completed|archived)$"),
    company_id: str | None = None,
    query: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    sessions, total = await svc.list_sessions(
        status=status,
        company_id=uuid.UUID(company_id) if company_id else None,
        query=query,
        skip=skip,
        limit=limit,
    )
    return sessions


@router.get("/sessions/{session_id}", response_model=ResearchSessionDetail)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    session = await svc.get_session(session_id, eager=True)
    return session


@router.patch("/sessions/{session_id}", response_model=ResearchSessionResponse)
async def update_session(
    session_id: uuid.UUID,
    data: ResearchSessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    session = await svc.update_session(session_id, **data.model_dump(exclude_unset=True))
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    await svc.delete_session(session_id)


# ── Evidence ────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/evidences", response_model=EvidenceResponse, status_code=201)
async def add_evidence(
    session_id: uuid.UUID,
    data: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    evidence = await svc.add_evidence(session_id, **data.model_dump())
    return evidence


@router.get("/sessions/{session_id}/evidences", response_model=list[EvidenceResponse])
async def list_evidences(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    return await svc.get_evidences(session_id)


@router.delete("/evidences/{evidence_id}", status_code=204)
async def delete_evidence(
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    await svc.remove_evidence(evidence_id)


# ── Reports ─────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/reports", response_model=ReportResponse, status_code=201)
async def create_report(
    session_id: uuid.UUID,
    title: str,
    content: str,
    format: str = "markdown",
    is_final: bool = False,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    report = await svc.create_report(
        session_id, title, content, format_=format, is_final=is_final
    )
    return report


@router.get("/sessions/{session_id}/reports", response_model=list[ReportResponse])
async def list_reports(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    return await svc.get_reports(session_id)


# ── Thesis / Finalize ──────────────────────────────────────────────

@router.post("/sessions/{session_id}/finalize", response_model=ResearchSessionResponse)
async def finalize_research(
    session_id: uuid.UUID,
    thesis: str,
    decision: str = Query(..., pattern="^(buy|sell|hold|watch|pass)$"),
    confidence: float = Query(..., ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    svc = ResearchService(db)
    return await svc.finalize_thesis(session_id, thesis, decision, confidence)


# ── AI-Assisted ─────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/auto-gather")
async def auto_gather(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Auto-search knowledge base and market data for evidence."""
    svc = ResearchService(db)
    count = await svc.auto_gather_evidence(session_id, db)
    return {"session_id": str(session_id), "evidences_added": count}
