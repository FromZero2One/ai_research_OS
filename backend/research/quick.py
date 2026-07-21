"""Quick Research — one-click research with real-time SSE progress.

Chains: Create Session → Plan → Gather Evidence → Generate Report
Progress updates are streamed via Server-Sent Events (SSE).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import get_db
from core.exceptions import NotFoundError
from research.models import ResearchSession
from research.service import ResearchService

router = APIRouter(prefix="/research/quick", tags=["Quick Research"])

PROGRESS_KEY = "quick_research_progress"


class QuickResearchRequest(BaseModel):
    ticker: str = Field(..., max_length=16)
    question: str = Field(..., min_length=10, max_length=1000)
    title: str | None = None


class QuickResearchResponse(BaseModel):
    session_id: str
    status: str = "started"


async def _get_company_by_ticker(ticker: str, db: AsyncSession) -> uuid.UUID | None:
    """Resolve ticker to company_id."""
    from company.models import Company
    result = await db.execute(
        select(Company).where(Company.ticker == ticker.upper()).limit(1)
    )
    company = result.scalar_one_or_none()
    return company.id if company else None


async def _get_progress(session_id: uuid.UUID, db: AsyncSession) -> dict[str, Any]:
    """Get current research progress from session metadata."""
    result = await db.execute(
        select(ResearchSession).where(ResearchSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return {"step": "error", "error": "Session not found"}

    progress = (session.extra_metadata or {}).get(PROGRESS_KEY, {})
    return {
        "step": progress.get("step", "starting"),
        "message": progress.get("message", ""),
        "status": session.status,
        "session_id": str(session.id),
        "report_id": progress.get("report_id"),
        "error": progress.get("error"),
    }


async def _update_progress(
    session_id: uuid.UUID,
    step: str,
    message: str,
    db: AsyncSession,
    **extra,
) -> None:
    """Update progress in session metadata."""
    result = await db.execute(
        select(ResearchSession).where(ResearchSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        return

    session.extra_metadata = session.extra_metadata or {}
    session.extra_metadata[PROGRESS_KEY] = {
        "step": step,
        "message": message,
        **extra,
    }
    await db.flush()


async def _run_research_chain(
    session_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Background task: run the full research chain with progress updates."""
    from core.database import async_session_factory

    # Use a separate session for the background task
    async with async_session_factory() as bg_session:
        svc = ResearchService(bg_session)

        try:
            # Step 2: Generate Plan
            await _update_progress(session_id, "planning", "AI 正在生成研究计划...", bg_session)
            await bg_session.commit()

            await svc.generate_plan(session_id)
            await bg_session.commit()  # ✅ commit before LLM call

            # Step 3: Gather Evidence
            await _update_progress(session_id, "searching", "正在搜索知识库和市场数据...", bg_session)
            await bg_session.commit()

            await svc.auto_gather_evidence(session_id, bg_session, use_plan=True)
            await bg_session.commit()

            # Step 4: Generate Report
            await _update_progress(session_id, "generating", "AI 正在生成研究报告...", bg_session)
            await bg_session.commit()

            report = await svc.auto_generate_report(session_id, is_final=False)
            await bg_session.commit()

            # Done
            await _update_progress(
                session_id, "completed", "研究完成！",
                bg_session,
                report_id=str(report.id),
            )
            await bg_session.commit()

        except Exception as e:
            await bg_session.rollback()
            await _update_progress(
                session_id, "error", f"研究过程出错: {str(e)[:200]}",
                bg_session,
                error=str(e),
            )
            await bg_session.commit()


# ── API Endpoints ─────────────────────────────────────────────────────


@router.post("", response_model=QuickResearchResponse)
async def quick_research(
    data: QuickResearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start a one-click research. Runs synchronously.

    Research chain executes in-band (not background task):
    plan → gather → generate report. May take 30-60s.
    """
    ticker = data.ticker.upper()
    title = data.title or f"{ticker} 快速研究"
    company_id = await _get_company_by_ticker(ticker, db)

    svc = ResearchService(db)
    session = await svc.create_session(
        title=title,
        question=data.question,
        company_id=company_id,
        auto_plan=False,
    )
    await db.commit()

    # Run research chain
    from core.logging import logger
    try:
        from core.database import async_session_factory

        async with async_session_factory() as bg_session:
            logger.info("Quick research: starting chain for %s", session.id)
            bg_svc = ResearchService(bg_session)

            # Step 1: Generate Plan
            await _update_progress(session.id, "planning", "AI 正在生成研究计划...", bg_session)
            await bg_session.commit()
            logger.info("Quick research: generating plan...")
            try:
                await bg_svc.generate_plan(session.id)
                await bg_session.commit()
                logger.info("Quick research: plan done")
            except Exception as e:
                logger.error("Plan generation failed: %s", e)
                raise

            # Step 2: Gather Evidence
            await _update_progress(session.id, "searching", "正在搜索知识库和市场数据...", bg_session)
            await bg_session.commit()
            logger.info("Quick research: gathering evidence...")
            try:
                await bg_svc.auto_gather_evidence(session.id, bg_session, use_plan=True)
                await bg_session.commit()
                logger.info("Quick research: evidence done")
            except Exception as e:
                logger.error("Evidence gathering failed: %s", e)
                raise

            # Step 3: Generate Report
            await _update_progress(session.id, "generating", "AI 正在生成研究报告...", bg_session)
            await bg_session.commit()
            logger.info("Quick research: generating report...")
            try:
                report = await bg_svc.auto_generate_report(session.id, is_final=False)
                await bg_session.commit()
                logger.info("Quick research: report done (id=%s)", report.id)
            except Exception as e:
                logger.error("Report generation failed: %s", e)
                raise

            await _update_progress(
                session.id, "completed", "研究完成！",
                bg_session, report_id=str(report.id),
            )
            await bg_session.commit()
            logger.info("Quick research: chain complete")
    except Exception as e:
        logger.error("Quick research chain failed: %s", e, exc_info=True)
        try:
            async with async_session_factory() as err_session:
                await _update_progress(
                    session.id, "error", f"研究过程出错: {str(e)[:200]}",
                    err_session, error=str(e),
                )
                await err_session.commit()
        except Exception:
            pass

    return QuickResearchResponse(
        session_id=str(session.id),
        status="started",
    )


@router.get("/{session_id}/stream")
async def stream_research_progress(session_id: uuid.UUID):
    """SSE endpoint: stream research progress in real-time.

    Yields events:
      event: progress\ndata: {"step": "planning", "message": "..."}
      event: complete\n data: {"session_id": "...", "report_id": "..."}
      event: error\ndata: {"error": "..."}
    """
    from core.database import async_session_factory

    async def event_generator():
        async with async_session_factory() as db:
            while True:
                progress = await _get_progress(session_id, db)

                if progress.get("error"):
                    yield f"event: error\ndata: {json.dumps(progress)}\n\n"
                    break

                if progress["step"] == "completed":
                    yield f"event: complete\ndata: {json.dumps(progress)}\n\n"
                    break

                yield f"event: progress\ndata: {json.dumps(progress)}\n\n"

                await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{session_id}/status")
async def get_quick_research_status(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Poll current research progress (non-SSE fallback)."""
    progress = await _get_progress(session_id, db)
    return progress
