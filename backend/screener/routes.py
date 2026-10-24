"""Screener API — 手动触发、运行历史、标准文档读写、规则缓存查看。"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
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
    save: bool = False
    name: str | None = Field(default=None, max_length=128)


class ToResearchParams(BaseModel):
    """POST /runs/{id}/to-research body。"""

    tickers: list[str] | None = None
    limit: int = Field(default=5, ge=1, le=50)


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
    from pathlib import Path

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


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """请求取消运行：worker 在阶段边界/下一只深判前 cooperative 停止。"""
    from screener.service import ACTIVE_STATUSES

    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    if run.status == "cancelling":
        return {"id": str(run.id), "status": run.status}
    if run.status not in ACTIVE_STATUSES:
        return JSONResponse(
            status_code=409, content={"error": f"运行已结束（{run.status}），无法取消"}
        )
    run.status = "cancelling"
    from screener.cancel import request_cancel

    request_cancel(run.id)
    await EventLogger(db).record(
        source="screener", event_type="screener.cancel_requested",
        entity_type="screener_run", entity_id=str(run.id),
        summary="用户请求取消运行",
    )
    await db.commit()
    return {"id": str(run.id), "status": run.status}


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


@router.get("/runs/{run_id}/export")
async def export_run(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """导出该轮全部判断为 CSV（UTF-8 BOM，Excel 可直接打开）。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    judgements = (
        await db.execute(
            select(ScreenerJudgement)
            .where(ScreenerJudgement.run_id == run_id)
            .order_by(ScreenerJudgement.created_at)
        )
    ).scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "代码", "名称", "结论", "推荐", "置信度", "行业", "现价", "总市值",
        "初筛得分", "命中预设", "理由", "标准命中", "状态", "错误",
    ])
    for j in judgements:
        snap = j.snapshot or {}
        recommend = "" if j.recommend is None else ("是" if j.recommend else "否")
        hits = "；".join(
            f"{h.get('criterion', '')}:{'命中' if h.get('hit') else '未命中'}"
            for h in (j.criteria_hits or [])
        )
        writer.writerow([
            j.ticker, j.name or "", j.verdict or "", recommend,
            "" if j.confidence is None else j.confidence,
            snap.get("industry") or "", snap.get("price") or "",
            snap.get("market_cap") or "", snap.get("score") or "",
            "、".join(snap.get("presets") or []),
            "；".join(j.reasons or []), hits, j.status, j.error or "",
        ])

    filename = f"screener-run-{str(run.id)[:8]}.csv"
    return Response(
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
        "webhook": {
            "enabled": bool(settings.SCREENER_WEBHOOK_URL),
            "format": settings.SCREENER_WEBHOOK_FORMAT,
            "notify_on": settings.SCREENER_WEBHOOK_NOTIFY_ON,
        },
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

    payload = {"run_id": str(run.id), **result}
    if params.save:
        from screener.portfolio_store import save_portfolio

        row = await save_portfolio(
            db,
            run.id,
            {
                "capital": params.capital,
                "method": params.method,
                "max_weight": params.max_weight,
                "max_industry_weight": params.max_industry_weight,
                "max_holdings": params.max_holdings,
            },
            result,
            name=params.name,
        )
        await db.commit()
        payload["portfolio_id"] = str(row.id)
        payload["name"] = row.name
    return payload


@router.get("/portfolios")
async def list_all_portfolios(db: AsyncSession = Depends(get_db)):
    """全部已保存组合（最新在前）。"""
    from screener.portfolio_store import list_portfolios, portfolio_json

    rows = await list_portfolios(db)
    return {"portfolios": [portfolio_json(p) for p in rows]}


@router.get("/runs/{run_id}/portfolios")
async def list_run_portfolios(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """某轮运行下已保存的组合方案。"""
    from screener.portfolio_store import list_portfolios, portfolio_json

    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    rows = await list_portfolios(db, run_id)
    return {"portfolios": [portfolio_json(p) for p in rows]}


@router.get("/portfolios/{portfolio_id}")
async def get_saved_portfolio(
    portfolio_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """已保存组合详情。"""
    from screener.portfolio_store import get_portfolio, portfolio_json

    row = await get_portfolio(db, portfolio_id)
    if row is None:
        raise NotFoundError("ScreenerPortfolio", str(portfolio_id))
    return portfolio_json(row)


@router.delete("/portfolios/{portfolio_id}", status_code=204)
async def remove_saved_portfolio(
    portfolio_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """删除已保存组合。"""
    from screener.portfolio_store import delete_portfolio

    if not await delete_portfolio(db, portfolio_id):
        raise NotFoundError("ScreenerPortfolio", str(portfolio_id))
    await db.commit()


@router.post("/runs/{run_id}/to-research")
async def to_research(
    run_id: uuid.UUID,
    params: ToResearchParams,
    db: AsyncSession = Depends(get_db),
):
    """为推荐股创建研究中心会话（默认取置信度最高的 5 只，不自动规划）。"""
    from screener.handoff import create_research_sessions

    try:
        return await create_research_sessions(
            db, run_id, tickers=params.tickers, limit=params.limit
        )
    except ValueError as e:
        raise NotFoundError("ScreenerRun", str(run_id)) from e


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
