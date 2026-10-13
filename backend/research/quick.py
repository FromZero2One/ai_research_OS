"""Quick Research — one-click research with persistent background task.

POST  → creates session + creates TaskRecord (persistent) → returns immediately
SSE  → streams progress from DB as the background task runs
Worker  → picks up pending TaskRecord, runs plan→gather→report chain
Supports retry on failure, survives process restart.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.container import Container
from core.database import get_container
from core.logging import logger
from core.task_manager import register_handler, run_in_background

router = APIRouter(tags=["Quick Research"])


class QuickResearchRequest(BaseModel):
    ticker: str = Field(..., max_length=16)
    question: str = Field(..., min_length=10, max_length=1000)
    title: str | None = None
    plan_type: str | None = Field(
        None, description="预置研究类型：initial/earnings/thesis_check/industry，命中模板零 LLM"
    )


class QuickResearchResponse(BaseModel):
    session_id: str
    status: str = "started"


# ── Handler (registered at import time) ──────────────────────────────────


async def _run_research_chain(payload: dict) -> dict | None:
    """Registered handler for 'quick_research' tasks.

    Receives payload from TaskRecord, runs plan→gather→report.
    Progress is persisted in session extra_metadata (survives restart).
    """
    session_id = uuid.UUID(payload["session_id"])
    from core.container import create_container
    from core.database import managed_session

    async with managed_session() as bg_session:
        container = create_container(bg_session)
        sessions_svc = container.research_session_service
        gather_svc = container.research_gather_service
        report_svc = container.research_report_service

        try:
            # Step 1: Generate Plan
            await sessions_svc.update_progress(session_id, "planning", "AI 正在生成研究计划...")
            await bg_session.commit()
            logger.info("  [research] planning %s", session_id)
            await sessions_svc.generate_plan(session_id)
            await bg_session.commit()

            # Step 2: Gather Evidence
            await sessions_svc.update_progress(
                session_id, "searching", "正在搜索知识库和市场数据..."
            )
            await bg_session.commit()
            logger.info("  [research] gathering %s", session_id)
            await gather_svc.auto_gather(session_id, use_plan=True)
            await bg_session.commit()

            # Step 3: Generate Report
            await sessions_svc.update_progress(session_id, "generating", "AI 正在生成研究报告...")
            await bg_session.commit()
            logger.info("  [research] generating %s", session_id)
            report = await report_svc.auto_generate(session_id, is_final=False)
            await bg_session.commit()

            # Done
            await sessions_svc.update_progress(
                session_id, "completed", "研究完成！", report_id=str(report.id)
            )
            await bg_session.commit()
            logger.info("  [research] completed %s (report=%s)", session_id, report.id)
            return {"report_id": str(report.id)}

        except asyncio.CancelledError:
            logger.warning("  [research] cancelled %s", session_id)
            await sessions_svc.update_progress(session_id, "error", "研究任务被取消")
            await bg_session.commit()
            return None
        except Exception as e:
            logger.error("  [research] failed %s: %s", session_id, e, exc_info=True)
            await sessions_svc.update_progress(
                session_id, "error", f"研究过程出错: {str(e)[:200]}", error=str(e)
            )
            await bg_session.commit()
            raise  # Re-raise so TaskRecord tracks the failure


# Register handler (import-time side effect — safe, no IO)
register_handler("quick_research", _run_research_chain)


# ── Helper ────────────────────────────────────────────────────────────────


async def _get_company_by_ticker(ticker: str, container: Container) -> uuid.UUID | None:
    """Resolve ticker to company_id."""
    company = await container.company_service.get_by_ticker(ticker)
    return company.id if company else None


# ── API Endpoints ─────────────────────────────────────────────────────


@router.post("", response_model=QuickResearchResponse)
async def quick_research(
    data: QuickResearchRequest,
    container: Container = Depends(get_container),
):
    """Start one-click research. Returns immediately; runs in background.

    The research chain (plan → gather → report) runs via the background
    task worker. Progress is streamed via SSE at GET /{id}/stream.
    The task is persistent — survives server restart.
    """
    ticker = data.ticker.upper()
    title = data.title or f"{ticker} 快速研究"
    company_id = await _get_company_by_ticker(ticker, container)

    sessions_svc = container.research_session_service
    session = await sessions_svc.create(
        title=title,
        question=data.question,
        company_id=company_id,
        auto_plan=False,
        plan_type=data.plan_type,
    )
    await container.session.commit()

    # Create persistent task — the POST returns immediately
    sid = str(session.id)
    created = await run_in_background(
        task_type="quick_research",
        task_key=sid,
        payload={"session_id": sid},
    )
    if created:
        logger.info("  [research] created persistent task %s", sid)
    else:
        logger.warning("  [research] task %s already running (dedup)", sid)

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
    from core.database import managed_session

    async def event_generator():
        async with managed_session() as db:
            from core.container import create_container

            sessions_svc = create_container(db).research_session_service

            deadline = time.time() + 120  # 2-minute timeout
            while time.time() < deadline:
                progress = await sessions_svc.get_progress(session_id)

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
async def get_quick_research_status(
    session_id: uuid.UUID,
    container: Container = Depends(get_container),
):
    """Poll current research progress (non-SSE fallback)."""
    svc = container.research_session_service
    progress = await svc.get_progress(session_id)
    return progress
