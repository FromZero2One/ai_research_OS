"""Quick Research — one-click research with async background execution.

POST  → creates session + fires background task → returns immediately
SSE  → streams progress from DB as the background task runs
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from research.models import ResearchSession
from core.logging import logger
from core.task_manager import track, untrack
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


async def _run_research_task(
    session_id: uuid.UUID,
) -> None:
    """Background task: run full research chain. Uses its own DB session."""
    from core.database import async_session_factory

    async with async_session_factory() as bg_session:
        svc = ResearchService(bg_session)

        try:
            # Step 1: Generate Plan
            await _update_progress(session_id, "planning", "AI 正在生成研究计划...", bg_session)
            await bg_session.commit()
            logger.info("  [research] planning %s", session_id)
            await svc.generate_plan(session_id)
            await bg_session.commit()

            # Step 2: Gather Evidence
            await _update_progress(session_id, "searching", "正在搜索知识库和市场数据...", bg_session)
            await bg_session.commit()
            logger.info("  [research] gathering %s", session_id)
            await svc.auto_gather_evidence(session_id, bg_session, use_plan=True)
            await bg_session.commit()

            # Step 3: Generate Report
            await _update_progress(session_id, "generating", "AI 正在生成研究报告...", bg_session)
            await bg_session.commit()
            logger.info("  [research] generating %s", session_id)
            report = await svc.auto_generate_report(session_id, is_final=False)
            await bg_session.commit()

            # Done
            await _update_progress(
                session_id, "completed", "研究完成！",
                bg_session, report_id=str(report.id),
            )
            await bg_session.commit()
            logger.info("  [research] completed %s (report=%s)", session_id, report.id)

        except asyncio.CancelledError:
            logger.warning("  [research] cancelled %s", session_id)
            await _update_progress(session_id, "error", "研究任务被取消", bg_session)
            await bg_session.commit()
        except Exception as e:
            logger.error("  [research] failed %s: %s", session_id, e, exc_info=True)
            await _update_progress(
                session_id, "error", f"研究过程出错: {str(e)[:200]}",
                bg_session, error=str(e),
            )
            await bg_session.commit()
        finally:
            untrack(str(session_id))


# ── API Endpoints ─────────────────────────────────────────────────────


@router.post("", response_model=QuickResearchResponse)
async def quick_research(
    data: QuickResearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Start one-click research. Returns immediately; runs in background.

    The research chain (plan → gather → generate) executes as an asyncio
    background task. Progress is streamed via SSE at GET /{id}/stream.
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

    # Fire background task — the POST returns immediately
    sid = str(session.id)
    track(sid)
    asyncio.create_task(_run_research_task(session.id))
    logger.info("  [research] fired background task %s", sid)

    return QuickResearchResponse(
        session_id=sid,
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
            deadline = time.time() + 120  # 2-minute timeout
            while time.time() < deadline:
                progress = await _get_progress(session_id, db)

                if progress.get("error"):
                    yield f"event: error\ndata: {json.dumps(progress)}\n\n"
                    return

                if progress["step"] == "completed":
                    yield f"event: complete\ndata: {json.dumps(progress)}\n\n"
                    return

                yield f"event: progress\ndata: {json.dumps(progress)}\n\n"

                await asyncio.sleep(0.5)

            yield f"event: error\ndata: {json.dumps({'error': '研究超时'})}\n\n"

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
