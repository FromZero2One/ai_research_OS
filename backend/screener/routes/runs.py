"""Screener 运行 API — 触发、历史、详情、报告、调度。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import Container
from core.database import get_container, get_db
from core.exceptions import NotFoundError
from screener.models import ScreenerJudgement, ScreenerRun

router = APIRouter(tags=["Screener"])


class TriggerParams(BaseModel):
    """POST /runs 必填 body — presets 是唯一运行入口（freeform 已删除）。"""

    mode: Literal["presets"]
    pool: str = "all"
    preset_ids: list[str] = Field(min_length=1)
    combine: str = "union"


_DQ_METRICS = (
    "roe", "revenue", "net_income", "operating_cash_flow",
    "total_assets", "roic", "fcff",
)
_PERIOD_RANK = {"Q1": 1, "Q2": 2, "Semi": 2, "Q3": 3, "Q4": 4, "Annual": 4}


@router.get("/data-quality")
async def data_quality(db: AsyncSession = Depends(get_db)):
    """选股前置数据质量：最新财务期/指标覆盖、行情覆盖、知识库状态与告警。"""
    from sqlalchemy import func
    from sqlalchemy import select as sa_select

    from company.models import Company
    from document.models import Document, DocumentChunk
    from market.models import FinancialMetric, StockPrice

    periods = (
        await db.execute(
            sa_select(FinancialMetric.fiscal_year, FinancialMetric.fiscal_period).distinct()
        )
    ).all()
    latest = max(
        periods,
        key=lambda p: (p[0], _PERIOD_RANK.get(p[1], 0)),
        default=None,
    )
    financial: dict = {"period": None, "tickers": 0, "metrics": {}}
    if latest is not None:
        year, period = latest
        financial["period"] = f"{year}{period}"
        financial["tickers"] = int(
            (
                await db.execute(
                    sa_select(func.count(func.distinct(FinancialMetric.ticker))).where(
                        FinancialMetric.fiscal_year == year,
                        FinancialMetric.fiscal_period == period,
                    )
                )
            ).scalar()
            or 0
        )
        counts = dict(
            (
                await db.execute(
                    sa_select(
                        FinancialMetric.metric_name,
                        func.count(func.distinct(FinancialMetric.ticker)),
                    )
                    .where(
                        FinancialMetric.fiscal_year == year,
                        FinancialMetric.fiscal_period == period,
                        FinancialMetric.metric_name.in_(_DQ_METRICS),
                    )
                    .group_by(FinancialMetric.metric_name)
                )
            ).all()
        )
        total = financial["tickers"] or 1
        financial["metrics"] = {
            key: {
                "count": int(counts.get(key, 0)),
                "coverage": round(counts.get(key, 0) / total, 4),
            }
            for key in _DQ_METRICS
        }

    a_share = Company.ticker.op("~")(r"^(60|00)")
    company_count = int(
        (
            await db.execute(
                sa_select(func.count()).select_from(Company).where(a_share)
            )
        ).scalar()
        or 0
    )
    bar_subq = (
        sa_select(StockPrice.ticker)
        .group_by(StockPrice.ticker)
        .having(func.count() >= 200)
        .subquery()
    )
    bars_count = int(
        (await db.execute(sa_select(func.count()).select_from(bar_subq))).scalar() or 0
    )
    last_price_date = (
        await db.execute(sa_select(func.max(StockPrice.date)))
    ).scalar()

    indexed_docs = int(
        (
            await db.execute(
                sa_select(func.count())
                .select_from(Document)
                .where(Document.is_indexed.is_(True))
            )
        ).scalar()
        or 0
    )
    chunks = int(
        (await db.execute(sa_select(func.count()).select_from(DocumentChunk))).scalar() or 0
    )

    price_coverage = round(bars_count / company_count, 4) if company_count else 0.0
    warnings: list[str] = []
    if indexed_docs == 0:
        warnings.append("知识库为空：含定性标准的预设会判为“数据不足”")
    if company_count and price_coverage < 0.5:
        warnings.append(
            f"行情覆盖偏低（{bars_count}/{company_count} 只具备 ≥200 根日线），"
            "推荐后表现与回测样本会不足"
        )
    if latest is None:
        warnings.append("财务指标库为空：无法执行量化初筛")

    return {
        "financial": financial,
        "prices": {
            "companies": company_count,
            "tickers_with_200_bars": bars_count,
            "coverage": price_coverage,
            "last_price_date": last_price_date.isoformat() if last_price_date else None,
        },
        "knowledge": {"indexed_documents": indexed_docs, "chunks": chunks},
        "warnings": warnings,
    }


@router.post("/runs", status_code=201)
async def trigger_run(
    container: Container = Depends(get_container),
    params: TriggerParams = ...,
):
    """触发一次智能选股（presets 模式，持久后台任务）。已有进行中的运行 → 409。

    body 必填且 mode="presets"；缺 body / 非法字段 → 422。
    """
    try:
        run = await container.screener_service.trigger_run(params.model_dump())
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    if run is None:
        return JSONResponse(status_code=409, content={"error": "已有筛选进行中，请等待完成后再触发"})
    return {
        "id": str(run.id), "status": run.status, "criteria_hash": run.criteria_hash,
        "mode": run.mode, "combine": run.combine_mode,
    }


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
                "verdict": j.verdict,
                "reasons": j.reasons, "criteria_hits": j.criteria_hits,
                "confidence": j.confidence, "snapshot": j.snapshot,
                "status": j.status, "error": j.error,
            }
            for j in judgements
        ],
    }


@router.get("/schedule")
async def get_schedule():
    """定时选股配置与调度状态（配置项只读，来自环境变量）。"""
    from core.config import settings
    from core.scheduler import get_scheduler_status

    status = get_scheduler_status()
    job = next(
        (j for j in status.get("jobs", []) if j.get("id") == "screener_schedule"),
        None,
    )
    return {
        "scheduler_running": status.get("running", False),
        "job": job,
        "schedule": settings.SCREENER_SCHEDULE,
        "presets": [
            t.strip()
            for t in (settings.SCREENER_SCHEDULE_PRESETS or "").split(",")
            if t.strip()
        ],
    }


@router.post("/schedule/run", status_code=202)
async def run_schedule_now(db: AsyncSession = Depends(get_db)):
    """把“立即运行定时选股”投递为持久后台任务，避免请求长时间阻塞。"""
    from core.task_manager import create_task

    key = f"screener-schedule:{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
    task = await create_task("screener_schedule", key, {}, db=db)
    if task is None:
        return JSONResponse(
            status_code=409, content={"error": "定时选股任务已在运行"}
        )
    return {"status": "queued", "task_id": str(task.id), "task_key": key}


@router.get("/latest-report")
async def get_latest_report(db: AsyncSession = Depends(get_db)):
    """最近一次 completed run 的报告 markdown（前端直载；无则 404）。"""
    from pathlib import Path

    run = (
        await db.execute(
            select(ScreenerRun)
            .where(ScreenerRun.status == "completed")
            .order_by(ScreenerRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if run is None or not run.report_path:
        raise NotFoundError("ScreenerReport", "latest")
    path = Path(run.report_path)
    if not path.exists():
        raise NotFoundError("ScreenerReport", str(run.id))
    return {"run_id": str(run.id), "report": path.read_text(encoding="utf-8")}


@router.get("/runs/{run_id}/report")
async def get_report(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """报告 markdown 原文。"""
    from pathlib import Path

    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None or not run.report_path:
        raise NotFoundError("ScreenerReport", str(run_id))
    path = Path(run.report_path)
    if not path.exists():
        raise NotFoundError("ScreenerReport", str(run_id))
    return {"report": path.read_text(encoding="utf-8")}
