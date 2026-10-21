"""Screener API — 手动触发、运行历史、标准文档读写、规则缓存查看。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import Container
from core.database import get_container, get_db
from core.exceptions import NotFoundError
from screener.criteria import read_criteria, write_criteria
from screener.models import ScreenerJudgement, ScreenerRule, ScreenerRun

router = APIRouter(prefix="/screener", tags=["Screener"])


class CriteriaUpdate(BaseModel):
    criteria: str


@router.post("/runs", status_code=201)
async def trigger_run(container: Container = Depends(get_container)):
    """触发一次智能选股（持久后台任务）。已有进行中的运行 → 409。"""
    run = await container.screener_service.trigger_run()
    if run is None:
        return JSONResponse(status_code=409, content={"error": "已有筛选进行中，请等待完成后再触发"})
    return {"id": str(run.id), "status": run.status, "criteria_hash": run.criteria_hash}


@router.get("/runs")
async def list_runs(db: AsyncSession = Depends(get_db)):
    """运行历史（最新在前）。"""
    runs = (
        await db.execute(select(ScreenerRun).order_by(ScreenerRun.created_at.desc()).limit(50))
    ).scalars().all()
    return {
        "runs": [
            {
                "id": str(r.id), "status": r.status, "criteria_hash": r.criteria_hash,
                "candidate_count": r.candidate_count, "result_count": r.result_count,
                "report_path": r.report_path, "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at,
            }
            for r in runs
        ]
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """运行详情 + 深判结果列表。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    judgements = (
        await db.execute(
            select(ScreenerJudgement).where(ScreenerJudgement.run_id == run_id).order_by(ScreenerJudgement.created_at)
        )
    ).scalars().all()
    return {
        "id": str(run.id), "status": run.status, "criteria_hash": run.criteria_hash,
        "rules": run.rules, "candidate_count": run.candidate_count,
        "result_count": run.result_count, "report_path": run.report_path,
        "error": run.error, "started_at": run.started_at, "finished_at": run.finished_at,
        "judgements": [
            {
                "ticker": j.ticker, "name": j.name, "recommend": j.recommend,
                "reasons": j.reasons, "criteria_hits": j.criteria_hits,
                "confidence": j.confidence, "snapshot": j.snapshot,
                "status": j.status, "error": j.error,
            }
            for j in judgements
        ],
    }


@router.get("/runs/{run_id}/report")
async def get_report(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """报告 markdown 原文。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None or not run.report_path:
        raise NotFoundError("ScreenerReport", str(run_id))
    from pathlib import Path

    path = Path(run.report_path)
    if not path.exists():
        raise NotFoundError("ScreenerReport", str(run_id))
    return {"report": path.read_text(encoding="utf-8")}


@router.get("/criteria")
async def get_criteria():
    """读取标准文档。"""
    return {"criteria": read_criteria()}


@router.put("/criteria")
async def update_criteria(data: CriteriaUpdate):
    """保存标准文档（文档 hash 变化会使规则翻译缓存自然失效）。"""
    write_criteria(data.criteria)
    return {"ok": True}


@router.get("/rules")
async def get_rules(db: AsyncSession = Depends(get_db)):
    """最近一次结构化规则翻译缓存（便于人工核对 LLM 理解是否正确）。"""
    rule = (
        await db.execute(select(ScreenerRule).order_by(ScreenerRule.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    if rule is None:
        return {"rules": None}
    return {"rules": rule.rules, "criteria_hash": rule.doc_hash}
