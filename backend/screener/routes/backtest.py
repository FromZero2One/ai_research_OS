"""Screener 回测 API — 触发、历史、详情、报告。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.event_service import EventLogger
from core.exceptions import NotFoundError
from core.task_manager import TaskRecord, create_task
from screener.models import CriteriaPreset, ScreenerBacktestRun

router = APIRouter(tags=["Screener"])


class BacktestParams(BaseModel):
    """POST /backtests body。"""

    preset_id: uuid.UUID
    years: int = Field(default=5, ge=1, le=10)


@router.post("/backtests", status_code=201)
async def trigger_backtest(data: BacktestParams, db: AsyncSession = Depends(get_db)):
    """触发一次预设历史回测（持久后台任务）。预设不存在 → 422；已有进行中 → 409。"""
    preset = (
        await db.execute(select(CriteriaPreset).where(CriteriaPreset.id == data.preset_id))
    ).scalar_one_or_none()
    if preset is None:
        return JSONResponse(status_code=422, content={"error": f"预设不存在: {data.preset_id}"})
    active = (
        await db.execute(
            select(ScreenerBacktestRun).where(
                ScreenerBacktestRun.status.in_(["pending", "running"])
            ).limit(1)
        )
    ).scalar_one_or_none()
    if active:
        # 崩溃/handler 缺失可能留下永远 pending 的 run：对应任务已结束则先收尾
        task = (
            await db.execute(
                select(TaskRecord)
                .where(
                    TaskRecord.task_type == "screener_backtest",
                    TaskRecord.task_key == f"backtest:{active.id}",
                )
                .order_by(TaskRecord.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if task is None or task.status in ("failed", "completed"):
            active.status = "failed"
            active.error = active.error or "回测任务未执行完成（handler 缺失或进程中断）"
            active.finished_at = datetime.now(UTC).isoformat()
            await db.flush()
        else:
            return JSONResponse(
                status_code=409, content={"error": "已有回测任务进行中，请等待完成后再触发"}
            )

    run = ScreenerBacktestRun(preset_id=data.preset_id, years=data.years, status="pending")
    db.add(run)
    await db.flush()

    await create_task("screener_backtest", f"backtest:{run.id}", {"run_id": str(run.id)}, db=db)
    await EventLogger(db).record(
        source="screener", event_type="backtest.triggered",
        entity_type="backtest_run", entity_id=str(run.id),
        summary=f"触发回测：{preset.name} {data.years}年",
    )
    return {"id": str(run.id), "status": run.status}


@router.get("/backtests")
async def list_backtests(db: AsyncSession = Depends(get_db)):
    """最近回测（最新在前，含预设名称与 summary）。"""
    rows = (
        await db.execute(
            select(ScreenerBacktestRun)
            .order_by(ScreenerBacktestRun.created_at.desc())
            .limit(50)
        )
    ).scalars().all()
    names = {
        p.id: p.name
        for p in (
            await db.execute(
                select(CriteriaPreset).where(
                    CriteriaPreset.id.in_([r.preset_id for r in rows])
                )
            )
        ).scalars().all()
    } if rows else {}
    return {
        "backtests": [
            {
                "id": str(r.id),
                "preset_id": str(r.preset_id),
                "preset_name": names.get(r.preset_id),
                "years": r.years,
                "status": r.status,
                "error": r.error,
                "summary": (r.result or {}).get("summary") if r.result else None,
                "report_path": r.report_path,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "finished_at": r.finished_at,
            }
            for r in rows
        ]
    }


@router.get("/backtests/{run_id}/report")
async def get_backtest_report(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """回测 Markdown 报告原文。"""
    run = (
        await db.execute(
            select(ScreenerBacktestRun).where(ScreenerBacktestRun.id == run_id)
        )
    ).scalar_one_or_none()
    if run is None or not run.report_path:
        raise NotFoundError("ScreenerBacktestRun", str(run_id))
    path = Path(run.report_path)
    if not path.exists():
        raise NotFoundError("ScreenerBacktestRun", str(run_id))
    return {"report": path.read_text(encoding="utf-8")}


@router.get("/backtests/{run_id}")
async def get_backtest(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """回测详情（含 result JSON 与报告路径）。"""
    run = (
        await db.execute(select(ScreenerBacktestRun).where(ScreenerBacktestRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerBacktestRun", str(run_id))
    return {
        "id": str(run.id), "preset_id": str(run.preset_id), "years": run.years,
        "status": run.status, "error": run.error, "result": run.result,
        "report_path": run.report_path,
    }
