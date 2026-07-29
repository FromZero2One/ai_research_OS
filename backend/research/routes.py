"""Research Center API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from research.evidence_service import EvidenceService
from research.gather_service import GatherService
from research.report_service import ReportService
from research.schemas import (
    EvidenceCreate,
    EvidenceResponse,
    ReportResponse,
    ResearchPlan,
    ResearchSessionCreate,
    ResearchSessionDetail,
    ResearchSessionResponse,
    ResearchSessionUpdate,
)
from research.session_service import SessionService

router = APIRouter(prefix="/research", tags=["Research Center"])


# ── Sessions ────────────────────────────────────────────────────────

@router.post("/sessions", response_model=ResearchSessionResponse, status_code=201)
async def create_session(
    data: ResearchSessionCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = SessionService(db)
    session = await svc.create(**data.model_dump())
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
    svc = SessionService(db)
    sessions, total = await svc.list(
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
    svc = SessionService(db)
    session = await svc.get(session_id, eager=True)
    return session


@router.patch("/sessions/{session_id}", response_model=ResearchSessionResponse)
async def update_session(
    session_id: uuid.UUID,
    data: ResearchSessionUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = SessionService(db)
    session = await svc.update(session_id, **data.model_dump(exclude_unset=True))
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = SessionService(db)
    await svc.delete(session_id)


# ── Evidence ────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/evidences", response_model=EvidenceResponse, status_code=201)
async def add_evidence(
    session_id: uuid.UUID,
    data: EvidenceCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = EvidenceService(db)
    evidence = await svc.add(session_id, **data.model_dump())
    return evidence


@router.get("/sessions/{session_id}/evidences", response_model=list[EvidenceResponse])
async def list_evidences(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = EvidenceService(db)
    return await svc.list(session_id)


@router.delete("/evidences/{evidence_id}", status_code=204)
async def delete_evidence(
    evidence_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = EvidenceService(db)
    await svc.remove(evidence_id)


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
    svc = ReportService(db)
    report = await svc.create(session_id, title, content, format_=format, is_final=is_final)
    return report


@router.get("/sessions/{session_id}/reports", response_model=list[ReportResponse])
async def list_reports(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = ReportService(db)
    return await svc.list(session_id)


# ── Research Plan ────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/plan", response_model=ResearchPlan)
async def generate_research_plan(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = SessionService(db)
    plan = await svc.generate_plan(session_id)
    return plan


@router.get("/sessions/{session_id}/plan", response_model=ResearchPlan | None)
async def get_research_plan(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    svc = SessionService(db)
    plan = await svc.get_plan(session_id)
    return plan


# ── AI Report Generation ────────────────────────────────────────────

@router.post("/sessions/{session_id}/generate-report", response_model=ReportResponse)
async def generate_report(
    session_id: uuid.UUID,
    is_final: bool = False,
    db: AsyncSession = Depends(get_db),
):
    svc = ReportService(db)
    report = await svc.auto_generate(session_id, is_final=is_final)
    return report


# ── Thesis / Finalize ──────────────────────────────────────────────

@router.post("/sessions/{session_id}/finalize", response_model=ResearchSessionResponse)
async def finalize_research(
    session_id: uuid.UUID,
    thesis: str,
    decision: str = Query(..., pattern="^(buy|sell|hold|watch|pass)$"),
    confidence: float = Query(..., ge=0.0, le=1.0),
    db: AsyncSession = Depends(get_db),
):
    from research.thesis_service import ThesisService
    svc = ThesisService(db)
    return await svc.finalize(session_id, thesis, decision, confidence)


# ── AI-Assisted ─────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/auto-gather")
async def auto_gather(
    session_id: uuid.UUID,
    use_plan: bool = True,
    db: AsyncSession = Depends(get_db),
):
    svc = GatherService(db)
    result = await svc.auto_gather(session_id, db, use_plan=use_plan)
    return result


# ── Include sub-routers (quick research + timeline) ─────────────────────

from research.quick import router as _quick_router  # noqa: E402
from research.timeline import router as _timeline_router  # noqa: E402

router.include_router(_quick_router, prefix="/quick")
router.include_router(_timeline_router)
