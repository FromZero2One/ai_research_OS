"""Screener 编排 — 触发、状态机推进、结果落库、报告落盘。

状态机：pending → screening → judging → completed/failed。
单只深判失败不拖垮整次运行（judge 层已隔离）；全链路异常 → run 置 failed。
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.llm import create_llm
from core.event_service import EventLogger
from core.logging import logger
from screener import screening
from screener.criteria import read_criteria
from screener.judge import judge_candidates
from screener.models import ScreenerJudgement, ScreenerRule, ScreenerRun
from screener.pool import filter_pool
from screener.report import build_report, report_path_for
from screener.rules_schema import hash_criteria
from screener.translate import get_or_translate_rules


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _reload_financials(db: AsyncSession) -> dict[str, list]:
    """加载全库财务指标 → {ticker: [FinancialMetricEntry]}（初筛求值用）。"""
    from market.domain import FinancialMetricEntry
    from market.models import FinancialMetric

    rows = (await db.execute(select(FinancialMetric))).scalars().all()
    financials: dict[str, list] = {}
    for m in rows:
        financials.setdefault(m.ticker, []).append(
            FinancialMetricEntry(
                fiscal_year=m.fiscal_year,
                fiscal_period=m.fiscal_period,
                metric_name=m.metric_name,
                metric_value=m.metric_value,
            )
        )
    return financials


async def trigger_run(db: AsyncSession) -> ScreenerRun | None:
    """手动触发一次筛选。已有 pending/running 时返回 None（路由转 409）。"""
    active = (
        await db.execute(
            select(ScreenerRun).where(ScreenerRun.status.in_(["pending", "screening", "judging"])).limit(1)
        )
    ).scalar_one_or_none()
    if active:
        return None

    text = read_criteria()
    run = ScreenerRun(criteria_hash=hash_criteria(text), criteria_text=text)
    db.add(run)
    await db.flush()

    # 持久后台任务（worker 循环拾取；测试环境由测试直接调 run_screener_by_id）
    from core.task_manager import create_task

    await create_task("screener_run", f"screener:{run.id}", {"run_id": str(run.id)}, db=db)

    await EventLogger(db).record(
        source="screener",
        event_type="screener.triggered",
        entity_type="screener_run",
        entity_id=str(run.id),
        summary=f"触发智能选股（hash={run.criteria_hash}）",
    )
    return run


async def run_screener(db: AsyncSession, run_id: uuid.UUID) -> ScreenerRun:
    """执行一次筛选全流程（4 步流水线）。任何异常 → run 置 failed 后原样抛出。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one()
    run.status = "screening"
    run.started_at = _now()
    await db.flush()

    try:
        # ① 翻译标准（hash 缓存）
        llm = create_llm()
        rules = await get_or_translate_rules(db, run.criteria_text, llm=llm)
        run.rules = rules
        await db.flush()

        # ② 确定性初筛：全市场快照 → 股票池过滤 → 量化规则 → 排名截断
        spot = await screening.fetch_market_spot()
        from company.models import Company

        watched = set(
            (await db.execute(
                select(Company.ticker).where(Company.is_active.is_(True))
            )).scalars().all()
        )
        pool = filter_pool(spot, rules.get("stock_pool", {"type": "all"}), watched)

        financials = await _reload_financials(db)

        passed, excluded_missing = screening.evaluate_quant_rules(pool, rules.get("quant_rules", []), financials)

        # 候选缺 bs/cf 类指标（资产负债表/现金流）→ 对初筛通过者补采后重筛一次
        from screener.ingest import ingest_single_company

        need_metrics = {r["metric"] for r in rules.get("quant_rules", [])}
        needs_bs_cf = bool(need_metrics & {"total_assets", "total_liabilities", "debt_to_equity", "current_ratio", "operating_cash_flow"})
        if needs_bs_cf and passed:
            await db.flush()
            for cand in passed[: rules.get("candidate_limit", 50)]:
                await ingest_single_company(db, cand["ticker"])
            financials = await _reload_financials(db)
            passed, excluded_missing = screening.evaluate_quant_rules(pool, rules.get("quant_rules", []), financials)

        candidates = screening.rank_candidates(passed, limit=rules.get("candidate_limit", 50))
        run.candidate_count = len(candidates)
        run.status = "judging"
        await db.flush()

        # ③ LLM 逐只深判（v1 不接知识库检索 — 见 ledger Ruling）
        judgements = await judge_candidates(
            llm, candidates, run.criteria_text, knowledge=None,
            qualitative=rules.get("qualitative_criteria", []),
            financials_by_ticker=financials,
        )
        for j in judgements:
            db.add(ScreenerJudgement(run_id=run.id, **j))
        await db.flush()

        # ④ 报告落盘 + 收尾
        report = build_report(
            {"id": str(run.id), "candidate_count": run.candidate_count,
             "result_count": sum(1 for j in judgements if j.get("recommend") is True)},
            judgements, run.criteria_text, excluded_missing,
        )
        path = report_path_for(str(run.id))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")

        run.result_count = sum(1 for j in judgements if j.get("recommend") is True)
        run.report_path = str(path)
        run.status = "completed"
        run.finished_at = _now()
        await EventLogger(db).record(
            source="screener", event_type="screener.completed",
            entity_type="screener_run", entity_id=str(run.id),
            summary=f"选股完成：候选 {run.candidate_count}，推荐 {run.result_count}",
        )
    except Exception as e:  # noqa: BLE001 — 全链路兜底：失败要可见
        run.status = "failed"
        run.error = str(e)
        run.finished_at = _now()
        logger.exception("选股运行失败 %s", run_id)
        await EventLogger(db).record(
            source="screener", event_type="screener.failed",
            entity_type="screener_run", entity_id=str(run.id), summary=str(e)[:500],
        )
    await db.flush()
    return run


class ScreenerService:
    """DI 容器薄包装 — 路由经容器取用（session 与请求一致）。"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def trigger_run(self) -> ScreenerRun | None:
        return await trigger_run(self.db)


async def run_screener_by_id(run_id: str) -> None:
    """后台任务/测试入口 — 自管 session 执行一次筛选。"""
    from core.database import managed_session

    async with managed_session() as session:
        await run_screener(session, uuid.UUID(run_id))
        await session.commit()


async def _handle_screener_run(payload: dict) -> dict | None:
    """task_manager worker handler。"""
    await run_screener_by_id(payload["run_id"])
    return {"run_id": payload["run_id"]}


from core.task_manager import register_handler  # noqa: E402

register_handler("screener_run", _handle_screener_run)
