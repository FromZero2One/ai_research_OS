"""Screener API — 手动触发、运行历史、标准文档读写、规则缓存查看。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import Container
from core.database import get_container, get_db
from core.event_service import EventLogger
from core.exceptions import NotFoundError
from screener.criteria import read_criteria, write_criteria
from screener.models import (
    CriteriaPreset,
    ScreenerBacktestRun,
    ScreenerJudgement,
    ScreenerRule,
    ScreenerRun,
)
from screener.presets import (
    BuiltinPresetError,
    create_preset,
    delete_preset,
    list_metrics,
    list_presets,
    update_preset,
)

router = APIRouter(prefix="/screener", tags=["Screener"])


class CriteriaUpdate(BaseModel):
    criteria: str


class PresetUpsert(BaseModel):
    name: str | None = None
    description: str | None = None
    style_tag: str | None = None
    quant_rules: list[dict] | None = None
    qualitative: list[str] | None = None
    suggested_pool: str | None = None
    is_active: bool | None = None


class TriggerParams(BaseModel):
    """POST /runs 可选 body — body 缺省或 {} 均为 v1 自由文本模式。"""

    mode: str | None = None
    pool: str = "all"
    preset_ids: list[str] = Field(default_factory=list)
    combine: str = "union"


class BacktestParams(BaseModel):
    """POST /backtests body。"""

    preset_id: uuid.UUID
    years: int = Field(default=5, ge=1, le=10)


class PortfolioParams(BaseModel):
    """POST /runs/{id}/portfolio body。"""

    capital: float = Field(default=1_000_000.0, gt=0)
    method: str = "equal"
    max_weight: float = Field(default=0.15, gt=0, le=1)
    max_industry_weight: float = Field(default=0.35, gt=0, le=1)
    max_holdings: int = Field(default=20, ge=1, le=100)


def _preset_json(p: CriteriaPreset) -> dict:
    return {
        "id": str(p.id), "name": p.name, "description": p.description,
        "style_tag": p.style_tag, "quant_rules": p.quant_rules,
        "qualitative": p.qualitative, "suggested_pool": p.suggested_pool,
        "is_builtin": p.is_builtin, "is_active": p.is_active,
    }


@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """指标定义库（按 category, key 排序，前端按分类分组）。"""
    metrics = await list_metrics(db)
    return {"metrics": [
        {"key": m.key, "name_cn": m.name_cn, "category": m.category,
         "data_source": m.data_source, "description": m.description}
        for m in metrics
    ]}


@router.get("/presets")
async def get_presets(include_inactive: bool = False, db: AsyncSession = Depends(get_db)):
    """预设列表（内置 + 自建）。"""
    presets = await list_presets(db, include_inactive=include_inactive)
    return {"presets": [_preset_json(p) for p in presets]}


@router.post("/presets", status_code=201)
async def post_preset(data: PresetUpsert, db: AsyncSession = Depends(get_db)):
    """新建用户预设。校验失败 → 422。"""
    try:
        preset = await create_preset(db, data.model_dump(exclude_none=True))
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    return _preset_json(preset)


@router.put("/presets/{preset_id}")
async def put_preset(preset_id: uuid.UUID, data: PresetUpsert, db: AsyncSession = Depends(get_db)):
    """更新预设；内置预设 → 409（复制后编辑）。"""
    try:
        preset = await update_preset(db, preset_id, data.model_dump(exclude_none=True))
    except BuiltinPresetError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    if preset is None:
        raise NotFoundError("CriteriaPreset", str(preset_id))
    return _preset_json(preset)


@router.delete("/presets/{preset_id}")
async def remove_preset(preset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除预设；内置预设 → 409。"""
    try:
        deleted = await delete_preset(db, preset_id)
    except BuiltinPresetError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    if not deleted:
        raise NotFoundError("CriteriaPreset", str(preset_id))
    return {"ok": True}


@router.post("/runs", status_code=201)
async def trigger_run(
    container: Container = Depends(get_container),
    params: TriggerParams | None = None,
):
    """触发一次智能选股（持久后台任务）。已有进行中的运行 → 409。"""
    try:
        run = await container.screener_service.trigger_run(
            params.model_dump() if params is not None and params.mode is not None else None
        )
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    if run is None:
        return JSONResponse(status_code=409, content={"error": "已有筛选进行中，请等待完成后再触发"})
    return {
        "id": str(run.id), "status": run.status, "criteria_hash": run.criteria_hash,
        "mode": run.mode, "combine": run.combine_mode,
    }


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
        return JSONResponse(status_code=409, content={"error": "已有回测任务进行中，请等待完成后再触发"})

    run = ScreenerBacktestRun(preset_id=data.preset_id, years=data.years, status="pending")
    db.add(run)
    await db.flush()

    from core.task_manager import create_task

    await create_task("screener_backtest", f"backtest:{run.id}", {"run_id": str(run.id)}, db=db)
    await EventLogger(db).record(
        source="screener", event_type="backtest.triggered",
        entity_type="backtest_run", entity_id=str(run.id),
        summary=f"触发回测：{preset.name} {data.years}年",
    )
    return {"id": str(run.id), "status": run.status}


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


@router.get("/runs/{run_id}/diff")
async def get_diff(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """变化日报：与同口径上一轮运行对比。"""
    from screener.diff_service import build_run_diff

    try:
        markdown, has_previous = await build_run_diff(db, run_id)
    except ValueError as e:
        raise NotFoundError("ScreenerRun", str(run_id)) from e
    return {"diff": markdown, "has_previous": has_previous}


@router.get("/runs/{run_id}/performance")
async def get_performance(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """推荐后表现：T+1 收盘买入，1/3/6/12 月等权收益与胜率。"""
    from screener.performance_service import build_run_performance

    try:
        return await build_run_performance(db, run_id)
    except ValueError as e:
        raise NotFoundError("ScreenerRun", str(run_id)) from e


@router.post("/runs/{run_id}/portfolio")
async def build_portfolio(
    run_id: uuid.UUID,
    params: PortfolioParams,
    db: AsyncSession = Depends(get_db),
):
    """推荐股 → 资金分配（单票/行业上限，约束冲突时保留现金）。"""
    from screener.portfolio import construct_portfolio

    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    judgements = (
        await db.execute(
            select(ScreenerJudgement).where(
                ScreenerJudgement.run_id == run.id,
                ScreenerJudgement.status == "ok",
                ScreenerJudgement.recommend.is_(True),
            )
        )
    ).scalars().all()
    candidates = []
    for j in judgements:
        snapshot = j.snapshot or {}
        candidates.append(
            {
                "ticker": j.ticker,
                "name": j.name,
                "industry": snapshot.get("industry"),
                "price": snapshot.get("price"),
                "score": snapshot.get("score"),
                "confidence": j.confidence,
            }
        )
    try:
        result = construct_portfolio(
            candidates,
            capital=params.capital,
            method=params.method,
            max_weight=params.max_weight,
            max_industry_weight=params.max_industry_weight,
            max_holdings=params.max_holdings,
        )
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    return {"run_id": str(run.id), **result}


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
