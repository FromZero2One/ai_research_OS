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
from screener.models import ScreenerJudgement, ScreenerRun
from screener.pool import filter_pool
from screener.report import build_report, report_path_for
from screener.rules_schema import hash_criteria
from screener.translate import get_or_translate_rules


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def _reload_financials(
    db: AsyncSession,
    metrics: set[str] | None = None,
    year: int | None = None,
    period: str | None = None,
) -> dict[str, list]:
    """加载财务指标 → {ticker: [FinancialMetricEntry]}（初筛求值用）。

    传 metrics/year/period 时在 SQL 层过滤（全市场多期数据全量加载会
    随财报季无限增长，内存和查询时间都不可持续）；不传保持旧行为全量加载。
    """
    from market.domain import FinancialMetricEntry
    from market.models import FinancialMetric

    stmt = select(FinancialMetric)
    if metrics:
        stmt = stmt.where(FinancialMetric.metric_name.in_(metrics))
    if year is not None:
        stmt = stmt.where(FinancialMetric.fiscal_year == year)
    if period is not None:
        stmt = stmt.where(FinancialMetric.fiscal_period == period)
    rows = (await db.execute(stmt)).scalars().all()
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


_YJBB_METRICS = frozenset({"roe", "gross_margin", "net_margin", "revenue", "net_income"})
_MAIN_FINANCE_METRICS = frozenset({
    "eps", "current_ratio", "quick_ratio", "asset_turnover",
    "inventory_turnover", "receivables_turnover",
    "revenue_growth", "net_income_growth",
})
_BS_CF_METRICS = frozenset({
    "total_assets", "total_liabilities", "debt_to_equity", "operating_cash_flow",
})
_MONTH_TO_PERIOD = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}
_PERIOD_RANK = {"Q1": 1, "Q2": 2, "Semi": 2, "Q3": 3, "Q4": 4, "Annual": 4}
_PERIOD_END = {
    "Q1": "03-31", "Q2": "06-30", "Semi": "06-30",
    "Q3": "09-30", "Q4": "12-31", "Annual": "12-31",
}


def _latest_fiscal() -> tuple[str, int, str]:
    """最近已披露报告期 (YYYYMMDD, year, Qn)。"""
    from screener.ingest import _latest_report_date

    date = _latest_report_date()
    return date, int(date[:4]), _MONTH_TO_PERIOD[int(date[4:6])]


async def _missing_metric_keys(
    db: AsyncSession, needed: set[str], year: int, period: str
) -> set[str]:
    """needed 中在指定报告期尚无数据的指标键。"""
    from market.models import FinancialMetric

    needed = set(needed) & (_YJBB_METRICS | _MAIN_FINANCE_METRICS | _BS_CF_METRICS)
    if not needed:
        return set()
    present = set(
        (
            await db.execute(
                select(FinancialMetric.metric_name)
                .where(
                    FinancialMetric.metric_name.in_(needed),
                    FinancialMetric.fiscal_year == year,
                    FinancialMetric.fiscal_period == period,
                )
                .distinct()
            )
        ).scalars().all()
    )
    return needed - present


async def _ensure_market_data(db: AsyncSession, needed: set[str]) -> bool:
    """按需补齐最新报告期的财务指标；返回是否发生入库（调用方需重新 reload）。

    缺数据会让量化规则直接排除候选，因此必须在初筛前补齐，而不是等
    `passed` 为空后再补。三类数据源互相隔离，单个失败只记录、不中断整次运行。
    """
    date, year, period = _latest_fiscal()
    changed = False

    async def _try(loader, label: str) -> bool:
        try:
            await db.flush()
            # SAVEPOINT 隔离：补采失败只回滚本次采集，不污染 run 所在事务
            async with db.begin_nested():
                await loader()
            return True
        except Exception as e:  # noqa: BLE001 — 数据源故障降级为“缺数据”
            logger.warning("%s 补采失败: %s", label, e)
            return False

    missing = await _missing_metric_keys(db, needed, year, period)
    if missing & _YJBB_METRICS:
        from screener.ingest import ingest_marketwide_yjbb

        changed |= await _try(lambda: ingest_marketwide_yjbb(db, date), "yjbb")

    missing = await _missing_metric_keys(db, needed, year, period)
    if missing & _MAIN_FINANCE_METRICS:
        from screener.ingest import ingest_marketwide_main_finance

        changed |= await _try(lambda: ingest_marketwide_main_finance(db, date), "F10 主要指标")

    missing = await _missing_metric_keys(db, needed, year, period)
    if missing & _BS_CF_METRICS:
        from screener.ingest import ingest_marketwide_bs_cf

        changed |= await _try(lambda: ingest_marketwide_bs_cf(db, date), "资产负债表/现金流")

    return changed


def _financial_asof(financials: dict[str, list]) -> str | None:
    """财务数据最新报告期（用于报告标注）。"""
    periods = {(e.fiscal_year, e.fiscal_period) for entries in financials.values() for e in entries}
    if not periods:
        return None
    year, period = max(periods, key=lambda p: (p[0], _PERIOD_RANK.get(p[1], 0)))
    end = _PERIOD_END.get(period)
    return f"{year}{period}（{year}-{end}）" if end else f"{year}{period}"


async def trigger_run(db: AsyncSession, params: dict | None = None) -> ScreenerRun | None:
    """手动触发一次筛选。已有 pending/running 时返回 None（路由转 409）。

    params 形如 {"mode": "presets", "pool": "all", "preset_ids": [...], "combine": "union"}；
    None = v1 自由文本模式（读 criteria.md，走 LLM 翻译）。
    preset_ids 引用不存在的预设 → ValueError（路由层转 422）。
    """
    active = (
        await db.execute(
            select(ScreenerRun).where(ScreenerRun.status.in_(["pending", "screening", "judging"])).limit(1)
        )
    ).scalar_one_or_none()
    if active:
        return None

    if params is None:
        text = read_criteria()
        run = ScreenerRun(criteria_hash=hash_criteria(text), criteria_text=text)
    else:
        from screener.models import CriteriaPreset

        mode = params.get("mode", "presets")
        preset_ids = params.get("preset_ids") or []
        combine = params.get("combine", "union")
        pool = params.get("pool", "all")
        if mode != "presets":
            raise ValueError(f"未知触发模式: {mode!r}")
        if combine not in {"union", "intersection", "flatten"}:
            raise ValueError(f"未知组合方式: {combine!r}")
        if not preset_ids:
            raise ValueError("presets 模式必须选择至少一个预设")
        # 去重保持顺序；非法 UUID 字符串在此转 422 而非 DB DataError 500
        preset_ids = list(dict.fromkeys(preset_ids))
        try:
            parsed_ids = [uuid.UUID(str(i)) for i in preset_ids]
        except (ValueError, AttributeError) as e:
            raise ValueError(f"preset_ids 含非法 UUID: {preset_ids}") from e
        rows = (
            await db.execute(
                select(CriteriaPreset).where(CriteriaPreset.id.in_(parsed_ids))
            )
        ).scalars().all()
        found = {str(r.id) for r in rows}
        missing = [str(i) for i in preset_ids if str(i) not in found]
        if missing:
            raise ValueError(f"预设不存在: {missing}")

        # 保持用户选择顺序；深判无定性条目时会回退用 criteria_text，
        # 因此把预设描述一并带上，避免退化成「预设组合（核心资产）」这类空泛标签。
        by_id = {str(r.id): r for r in rows}
        ordered = [by_id[str(i)] for i in parsed_ids if str(i) in by_id]
        names = " + ".join(r.name for r in ordered)
        criteria_text = f"预设组合（{combine}）：{names}"
        descriptions = "；".join(f"{r.name}：{r.description}" for r in ordered if r.description)
        if descriptions:
            criteria_text += f"\n投资逻辑：{descriptions}"
        run = ScreenerRun(
            criteria_hash=hash_criteria(criteria_text + "|" + "|".join(sorted(found))),
            criteria_text=criteria_text,
            mode="presets",
            preset_ids=[str(i) for i in parsed_ids],
            combine_mode=combine,
            pool_override=pool,
        )
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
        # ① 标准来源：presets 模式纯函数组装（零 LLM）；自由文本走 LLM 翻译（hash 缓存）
        llm = create_llm()
        presets = None
        if run.mode == "presets":
            from screener.compose import compose_rules
            from screener.models import CriteriaPreset

            rows = (
                await db.execute(
                    select(CriteriaPreset).where(CriteriaPreset.id.in_(run.preset_ids))
                )
            ).scalars().all()
            by_id = {str(p.id): p for p in rows}
            missing = [i for i in run.preset_ids if i not in by_id]
            if missing:
                raise ValueError(f"预设已不存在（触发后被删除）: {missing}")
            presets = [by_id[i] for i in run.preset_ids]
            rules = compose_rules(presets, run.pool_override or "all", run.combine_mode or "union")
            rules["preset_ids"] = run.preset_ids
        else:
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

        # 先补齐所需财务指标，再做确定性初筛：缺数据会让规则直接排除候选，
        # 因此不能等 passed 为空后再补采。
        if run.mode == "presets":
            needed_metrics = {r["metric"] for p in presets for r in p.quant_rules}
        else:
            needed_metrics = {r["metric"] for r in rules.get("quant_rules", [])}
        await _ensure_market_data(db, needed_metrics)
        # 按「所需指标 × 最新报告期」过滤加载（全市场多期数据全量加载不可持续）
        _date, _year, _period = _latest_fiscal()
        financials = await _reload_financials(
            db, metrics=needed_metrics, year=_year, period=_period
        )

        if run.mode == "presets" and run.combine_mode == "union":
            # union：每个预设独立初筛 → 票数排名（hits ↓ → score ↓ → 市值 ↓）
            from screener.compose import evaluate_quant_rules_by_preset

            union_map = evaluate_quant_rules_by_preset(pool, presets, financials)
            spot_by_ticker = {c["ticker"]: c for c in pool}
            ranked = sorted(
                union_map.values(),
                key=lambda e: (
                    e["hits"],
                    e["score"],
                    spot_by_ticker.get(e["ticker"], {}).get("market_cap") or 0.0,
                ),
                reverse=True,
            )
            candidates = [
                {**spot_by_ticker[e["ticker"]], **e}
                for e in ranked[: rules.get("candidate_limit", 50)]
            ]
            excluded_missing: list[dict] = []
        else:
            passed, excluded_missing = screening.evaluate_quant_rules(
                pool, rules.get("quant_rules", []), financials
            )
            candidates = screening.rank_candidates(
                passed, limit=rules.get("candidate_limit", 50)
            )
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
            financial_asof=_financial_asof(financials),
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

    async def trigger_run(self, params: dict | None = None) -> ScreenerRun | None:
        return await trigger_run(self.db, params)


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
