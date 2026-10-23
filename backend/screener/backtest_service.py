"""回测编排 — 状态机推进、数据准备、逐期选股结算、结果落库。

状态机：pending → running → completed/failed。无 LLM 调用。
口径见 backtest.py / spec 2026-10-23：qfq 收盘价、年报口径（4 月用上一年 Q4）、
近似市值 = 调仓日收盘价 × 当前总股本（报告声明）、未计交易费用。
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from core.logging import logger
from screener import backtest, backtest_data
from screener.models import CriteriaPreset, ScreenerBacktestRun
from screener.report import report_path_for

# 模块级别名（测试 monkeypatch 目标 + 计划约定的接口名）
fetch_daily_from_mysql = backtest_data.fetch_daily_from_mysql
ensure_financial_periods = backtest_data.ensure_financial_periods
fetch_index_daily = backtest_data.fetch_index_daily

# 财务指标按报告期的内存索引：{(year, period): {ticker: [FinancialMetricEntry]}}


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


async def _load_financials_by_period(
    db: AsyncSession, periods: list[tuple[int, str]]
) -> dict[tuple[int, str], dict[str, list]]:
    """{(year, period): {ticker: [FinancialMetricEntry]}}（仅所需报告期）。"""
    from market.domain import FinancialMetricEntry
    from market.models import FinancialMetric

    out: dict[tuple[int, str], dict[str, list]] = defaultdict(dict)
    for year, period in periods:
        rows = (
            await db.execute(
                select(FinancialMetric).where(
                    FinancialMetric.fiscal_year == year,
                    FinancialMetric.fiscal_period == period,
                )
            )
        ).scalars().all()
        by_ticker: dict[str, list] = defaultdict(list)
        for m in rows:
            by_ticker[m.ticker].append(
                FinancialMetricEntry(
                    fiscal_year=m.fiscal_year, fiscal_period=m.fiscal_period,
                    metric_name=m.metric_name, metric_value=m.metric_value,
                )
            )
        out[(year, period)] = dict(by_ticker)
    return dict(out)


async def _fetch_total_shares(db: AsyncSession, tickers: list[str]) -> dict[str, float]:
    """当前总股本（近似市值用）：外部库 stock_value_entity 单日快照 → 本地无缓存直接拉。

    返回 {ticker: 总股本}；缺失的票不在返回中（该票 market_cap=None）。
    """
    import asyncio

    from market.akshare_executor import _AKSHARE_PROLOGUE, _run_child

    code = (
        _AKSHARE_PROLOGUE
        + "import akshare as ak, json\n"
        + "df = ak.stock_zh_a_spot_em()\n"
        + 'cols = {"代码": "ticker", "总股本": "shares"}\n'
        + "df = df[list(cols)].rename(columns=cols)\n"
        + 'print("__R__:" + json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str))\n'
    )
    raw = await asyncio.to_thread(_run_child, code, 300)
    if not raw or raw.startswith("E:"):
        logger.warning("总股本拉取失败，市值规则将全部缺数据: %s", (raw or "")[:200])
        return {}
    import json as _json

    rows = _json.loads(raw.removeprefix("__R__:").strip())
    want = set(tickers)
    out: dict[str, float] = {}
    for r in rows:
        t = str(r.get("ticker", "")).strip()
        if t in want and r.get("shares") not in (None, "", "-"):
            try:
                out[t] = float(r["shares"])
            except (TypeError, ValueError):
                continue
    return out


async def _price_dates_from_pg(db: AsyncSession, start: dt.date, end: dt.date) -> list[dt.date]:
    """区间内实际交易日历（从已灌入的日线推导）。"""
    from market.models import StockPrice

    rows = (
        await db.execute(
            select(StockPrice.date).where(
                StockPrice.date >= start, StockPrice.date <= end
            ).distinct().order_by(StockPrice.date)
        )
    ).scalars().all()
    return list(rows)


async def _load_day_closes(
    db: AsyncSession, day: dt.date, tickers: list[str]
) -> dict[str, float]:
    """某交易日各票前复权收盘价。"""
    from market.models import StockPrice

    rows = (
        await db.execute(
            select(StockPrice.ticker, StockPrice.close).where(
                StockPrice.date == day, StockPrice.ticker.in_(tickers)
            )
        )
    ).all()
    return {t: c for t, c in rows if c is not None}


async def run_backtest(db: AsyncSession, run_id) -> ScreenerBacktestRun:
    """执行回测全流程。任何异常 → run 置 failed 后原样抛出。"""
    run = (
        await db.execute(select(ScreenerBacktestRun).where(ScreenerBacktestRun.id == run_id))
    ).scalar_one()
    run.status = "running"
    run.started_at = _now_iso()
    await db.flush()

    try:
        preset = (
            await db.execute(select(CriteriaPreset).where(CriteriaPreset.id == run.preset_id))
        ).scalar_one_or_none()
        if preset is None:
            raise ValueError(f"预设不存在: {run.preset_id}")

        end = dt.date.today()
        start = end.replace(year=end.year - run.years)

        # ① 调仓日序列（需要先有日历 → 先拉全市场日线）
        #    票池：本地活跃公司；本地为空 → 外部库区间内 distinct symbol（含退市票）
        from company.models import Company

        tickers = set(
            (await db.execute(select(Company.ticker).where(Company.is_active.is_(True))))
            .scalars().all()
        )
        if not tickers:
            tickers = set(await backtest_data.fetch_all_tickers(start, end))
            logger.info("本地无活跃公司，票池来自外部库 distinct symbol：%d 只", len(tickers))
        # 逐只拉取并立即落库（拉一只灌一只，本地库行数即进度，中断可续）
        synced_tickers = await fetch_daily_from_mysql(db, sorted(tickers), start, end)
        if synced_tickers == 0 and not await _price_dates_from_pg(db, start, end):
            raise ValueError("外部日线数据为空（BACKTEST_MYSQL_URL 或外部库不可用）")
        await db.flush()
        logger.info("回测日线本次落库 %d 只", synced_tickers)

        price_dates = await _price_dates_from_pg(db, start, end)
        if not price_dates:
            raise ValueError("无价格日历（灌库后仍为空）")
        rebalance_dates = backtest.generate_rebalance_dates(price_dates, start, end)

        # ② 历史财务：各调仓日前最近已披露报告期（年报口径）
        periods = sorted({backtest.pick_financial_period(d) for d in rebalance_dates})
        await ensure_financial_periods(db, periods)
        financials_by_period = await _load_financials_by_period(db, periods)

        # ③ 近似市值用的当前总股本
        all_tickers = sorted(tickers)
        shares = await _fetch_total_shares(db, all_tickers)

        # ④ 逐调仓期：选股 → 买入/卖出结算 → 期收益
        periods_result: list[dict] = []
        for i, rdate in enumerate(rebalance_dates):
            fp = backtest.pick_financial_period(rdate)
            fin = financials_by_period.get(fp, {})

            # 当日快照行：价格 + 近似市值（收盘价 × 当前总股本）
            closes = await _load_day_closes(db, rdate, all_tickers)
            snapshot_rows = []
            for t, close in closes.items():
                shares_n = shares.get(t)
                snapshot_rows.append({
                    "ticker": t,
                    "name": t,
                    "price": close,
                    "market_cap": close * shares_n if shares_n else None,
                    "turnover": None,
                })

            portfolio, _excluded = backtest.select_portfolio(
                rdate, preset.quant_rules, snapshot_rows, fin, limit=20
            )
            if not portfolio:
                periods_result.append({
                    "year": rdate.year, "rebalance_date": rdate.isoformat(),
                    "return": 0.0, "bench": 0.0, "holdings": [],
                })
                continue

            # 卖出日 = 下一调仓日；末期持有到最后一个交易日
            sell_date = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else price_dates[-1]
            buy_prices = await _load_day_closes(db, rdate, [c["ticker"] for c in portfolio])
            sell_prices = await _load_day_closes(db, sell_date, [c["ticker"] for c in portfolio])
            holdings = backtest.compute_holding_returns(portfolio, buy_prices, sell_prices)
            period_ret = sum(h["return"] for h in holdings) / len(holdings)

            # 基准同期收益
            bench = await fetch_index_daily(start, end)
            bench_ret = _bench_return(bench, rdate, sell_date)

            periods_result.append({
                "year": rdate.year, "rebalance_date": rdate.isoformat(),
                "return": period_ret, "bench": bench_ret,
                "holdings": [
                    {k: h[k] for k in ("ticker", "name", "buy", "sell", "return", "suspended")}
                    for h in holdings
                ],
            })

        # ⑤ 汇总 + 落库（设计约定形状：{"summary": {...}, "yearly": [...]})
        stats = backtest.compute_nav_and_stats(periods_result)
        result = {
            "summary": {k: v for k, v in stats.items() if k != "yearly"},
            "yearly": stats["yearly"],
        }
        result["preset_name"] = preset.name
        result["start"] = start.isoformat()
        result["end"] = end.isoformat()
        result["disclaimers"] = [
            "未计交易费用与滑点",
            "市值为近似值：调仓日收盘价 × 当前总股本",
            "存在幸存者偏差：已退市股票可能不在数据源中",
            "财务数据按披露截止日近似可见性（实际披露日有早有晚）",
        ]
        run.result = result

        from screener.backtest_report import build_backtest_report

        report = build_backtest_report(run_id=str(run.id), preset_name=preset.name, result=result)
        path = report_path_for(f"backtest_{run.id}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        run.report_path = str(path)

        run.status = "completed"
        run.finished_at = _now_iso()
        await EventLogger(db).record(
            source="screener", event_type="backtest.completed",
            entity_type="backtest_run", entity_id=str(run.id),
            summary=f"回测完成：{preset.name} {run.years}年，{result['summary']['periods_count']} 期，累计 {result['summary']['total_return']:.1%}",
        )
    except Exception as e:  # noqa: BLE001 — 全链路兜底：失败要可见
        run.status = "failed"
        run.error = str(e)
        run.finished_at = _now_iso()
        logger.exception("回测失败 %s", run_id)
        await EventLogger(db).record(
            source="screener", event_type="backtest.failed",
            entity_type="backtest_run", entity_id=str(run.id), summary=str(e)[:500],
        )
    await db.flush()
    return run


def _bench_return(bench: list[dict], buy_day: dt.date, sell_day: dt.date) -> float:
    """基准在 [buy_day, sell_day] 的收益（取区间内首末收盘）。"""
    in_window = [b["close"] for b in bench if buy_day <= b["date"] <= sell_day]
    if len(in_window) < 2 or not in_window[0]:
        return 0.0
    return in_window[-1] / in_window[0] - 1.0


async def run_backtest_by_id(run_id: str) -> None:
    """后台任务入口 — 自管 session。"""
    from core.database import managed_session

    async with managed_session() as session:
        await run_backtest(session, uuid.UUID(run_id))
        await session.commit()


async def _handle_backtest_run(payload: dict) -> dict | None:
    await run_backtest_by_id(payload["run_id"])
    return {"run_id": payload["run_id"]}


from core.task_manager import register_handler  # noqa: E402

register_handler("screener_backtest", _handle_backtest_run)
