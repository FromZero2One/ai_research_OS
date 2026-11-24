"""回测编排 — 状态机推进、数据准备、逐期选股结算、结果落库。

状态机：pending → running → completed/failed。无 LLM 调用。
口径见 backtest.py / spec 2026-10-23：qfq 收盘价、年报口径（4 月用上一年 Q4）、
近似市值 = 调仓日收盘价 × 当前总股本（报告声明）、已计佣金/印花税/滑点、
财务可见性按公告日过滤（缺失公告日回退披露截止日）。
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
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
    db: AsyncSession,
    periods: list[tuple[int, str]],
    asof_by_period: dict[tuple[int, str], dt.date] | None = None,
) -> dict[tuple[int, str], dict[str, list]]:
    """{(year, period): {ticker: [FinancialMetricEntry]}}（仅所需报告期）。

    Point-in-Time（截止日口径）：报告期法定披露截止日之后的调仓才可见。
    东财 yjbb 的“最新公告日期”是**滚动最新值**（历史期会被污染成后续期公告日），
    因此把公告日钳制到报告期截止日，避免历史期被整体误排除；缺失公告日同样按
    截止日处理（回测报告会声明口径）。
    """
    from market.domain import FinancialMetricEntry
    from market.models import FinancialMetric

    deadlines = backtest.build_disclosure_map()
    out: dict[tuple[int, str], dict[str, list]] = defaultdict(dict)
    for year, period in periods:
        rows = (
            (
                await db.execute(
                    select(FinancialMetric).where(
                        FinancialMetric.fiscal_year == year,
                        FinancialMetric.fiscal_period == period,
                    )
                )
            )
            .scalars()
            .all()
        )

        deadline = deadlines.get((year, period))
        # 同票同期取最晚公告日（期末报告/更正），作为该票该期的可见日
        announcements: dict[str, dt.date] = {}
        for m in rows:
            if m.announcement_date is None:
                continue
            previous = announcements.get(m.ticker)
            if previous is None or m.announcement_date > previous:
                announcements[m.ticker] = m.announcement_date

        asof = (asof_by_period or {}).get((year, period))
        by_ticker: dict[str, list] = defaultdict(list)
        for m in rows:
            announced = m.announcement_date or announcements.get(m.ticker)
            # 滚动公告日 → 钳制到本期披露截止日（截止日为空则沿用原值）
            if deadline is not None and announced is not None and announced > deadline:
                announced = deadline
            if asof is not None and announced is not None and announced > asof:
                continue
            by_ticker[m.ticker].append(
                FinancialMetricEntry(
                    fiscal_year=m.fiscal_year,
                    fiscal_period=m.fiscal_period,
                    metric_name=m.metric_name,
                    metric_value=m.metric_value,
                    announcement_date=m.announcement_date,
                )
            )
        out[(year, period)] = dict(by_ticker)
    return dict(out)


def _fetch_shares_sync(url: str) -> dict[str, float]:
    """外部库最新交易日的总股本快照（symbol → TOTAL_SHARES）。"""
    import pymysql

    from screener.backtest_data import (
        _parse_db,
        _parse_host,
        _parse_password,
        _parse_port,
        _parse_user,
    )

    conn = pymysql.connect(
        host=_parse_host(url),
        user=_parse_user(url),
        password=_parse_password(url),
        database=_parse_db(url),
        port=_parse_port(url),
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT v.symbol, v.TOTAL_SHARES FROM akshare.stock_value_entity v "
                "JOIN (SELECT max(TRADE_DATE) d FROM akshare.stock_value_entity) m "
                "ON v.TRADE_DATE = m.d "
                "WHERE v.TOTAL_SHARES IS NOT NULL AND v.TOTAL_SHARES > 0"
            )
            return {str(sym).strip(): float(sh) for sym, sh in cur.fetchall()}
    finally:
        conn.close()


async def _fetch_total_shares(db: AsyncSession, tickers: list[str]) -> dict[str, float]:
    """当前总股本（近似市值用）：外部库 stock_value_entity 最新快照优先，akshare 兜底。

    返回 {ticker: 总股本}；缺失的票不在返回中（该票 market_cap=None）。
    """
    import asyncio

    from core.config import settings

    want = set(tickers)
    if settings.BACKTEST_MYSQL_URL:
        try:
            all_shares = await asyncio.to_thread(_fetch_shares_sync, settings.BACKTEST_MYSQL_URL)
            out = {t: all_shares[t] for t in want if all_shares.get(t, 0) > 0}
            if out:
                logger.info("总股本：外部库快照命中 %d/%d 只", len(out), len(want))
                return out
            logger.warning("外部库总股本快照为空，回退 akshare")
        except Exception as e:  # noqa: BLE001 — 外部库失败回退 akshare
            logger.warning("外部库总股本拉取失败，回退 akshare: %s", str(e)[:150])

    # 兜底：akshare 东财快照（可能被风控，失败则市值规则整体缺数据）
    from screener.ingest import _AKSHARE_PROLOGUE, _run_child

    code = (
        _AKSHARE_PROLOGUE
        + "import akshare as ak, json\n"
        + "df = ak.stock_zh_a_spot_em()\n"
        + 'cols = {"代码": "ticker", "总股本": "shares"}\n'
        + "df = df[list(cols)].rename(columns=cols)\n"
        + 'print("__R__:" + json.dumps(df.to_dict(orient="records"), '
        'ensure_ascii=False, default=str))\n'
    )
    try:
        rows = await asyncio.to_thread(_run_child, code, 300)
    except Exception as e:  # noqa: BLE001 — 兜底数据源失败不应毁掉整个回测
        logger.warning("总股本兜底拉取失败，市值规则将缺数据: %s", str(e)[:150])
        return {}
    if not rows:
        logger.warning("总股本拉取失败，市值规则将全部缺数据")
        return {}
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
        (
            await db.execute(
                select(StockPrice.date)
                .where(StockPrice.date >= start, StockPrice.date <= end)
                .distinct()
                .order_by(StockPrice.date)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _load_day_closes(db: AsyncSession, day: dt.date, tickers: list[str]) -> dict[str, float]:
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


async def _load_day_volumes(
    db: AsyncSession, day: dt.date, tickers: list[str]
) -> dict[str, float | None]:
    """某交易日成交量（用于停牌/不可交易判断）。"""
    from market.models import StockPrice

    rows = (
        await db.execute(
            select(StockPrice.ticker, StockPrice.volume).where(
                StockPrice.date == day, StockPrice.ticker.in_(tickers)
            )
        )
    ).all()
    return {t: v for t, v in rows}


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
        #    票池：预设回测面向全市场（外部库区间内 distinct symbol，含退市票，缓解幸存者偏差）；
        #    本地活跃公司（自选）足够多时才按自选票池回测。
        from company.models import Company

        MIN_ACTIVE_UNIVERSE = 100
        active = set(
            (await db.execute(select(Company.ticker).where(Company.is_active.is_(True))))
            .scalars()
            .all()
        )
        market = set(await backtest_data.fetch_all_tickers(start, end))
        if len(active) >= MIN_ACTIVE_UNIVERSE:
            overlap = active & market
            if len(overlap) >= MIN_ACTIVE_UNIVERSE:
                tickers = overlap
                logger.info("票池=活跃公司 ∩ 外部日线：%d 只", len(tickers))
            else:
                tickers = market
                logger.info(
                    "活跃公司与外部日线交集过小（%d 只），改用全市场：%d 只",
                    len(overlap),
                    len(market),
                )
        else:
            tickers = market
            logger.info(
                "活跃公司票池过小（%d 只），改用全市场票池：%d 只", len(active), len(market)
            )
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

        # ② 历史财务：各调仓日前最近已披露报告期（年报口径）+ PIT 公告日过滤
        periods = sorted({backtest.pick_financial_period(d) for d in rebalance_dates})
        await ensure_financial_periods(db, periods)
        asof_by_period: dict[tuple[int, str], dt.date] = {}
        for d in rebalance_dates:
            fp = backtest.pick_financial_period(d)
            asof_by_period[fp] = min(asof_by_period.get(fp, d), d)
        financials_by_period = await _load_financials_by_period(db, periods, asof_by_period)

        # ③ 近似市值用的当前总股本
        all_tickers = sorted(tickers)
        shares = await _fetch_total_shares(db, all_tickers)

        # 行业隔离（与实盘一致）：工业预设排除金融股，金融预设只看金融股
        from market.models import StockIndustry

        industry_map = {
            t: name
            for t, name in (
                await db.execute(select(StockIndustry.ticker, StockIndustry.industry_name))
            ).all()
        }
        FINANCIAL_STYLES = {"financial", "bank", "insurance"}
        scope = preset.style_tag if preset.style_tag in FINANCIAL_STYLES else "industrial"
        logger.info("回测行业隔离 scope=%s（%d 只有行业分类）", scope, len(industry_map))

        # 基准指数只拉取一次，所有调仓期复用（避免在循环内重复请求 akshare）
        bench = await fetch_index_daily(start, end)

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
                snapshot_rows.append(
                    {
                        "ticker": t,
                        "name": t,
                        "price": close,
                        "market_cap": close * shares_n if shares_n else None,
                        "turnover": None,
                        "industry": industry_map.get(t),
                    }
                )

            portfolio, _excluded = backtest.select_portfolio(
                rdate, preset.quant_rules, snapshot_rows, fin, limit=20, scope=scope
            )
            if not portfolio:
                periods_result.append(
                    {
                        "year": rdate.year,
                        "rebalance_date": rdate.isoformat(),
                        "return": 0.0,
                        "bench": 0.0,
                        "holdings": [],
                    }
                )
                continue

            # 卖出日 = 下一调仓日；末期持有到最后一个交易日
            sell_date = rebalance_dates[i + 1] if i + 1 < len(rebalance_dates) else price_dates[-1]
            held_tickers = [c["ticker"] for c in portfolio]
            buy_prices = await _load_day_closes(db, rdate, held_tickers)
            sell_prices = await _load_day_closes(db, sell_date, held_tickers)
            buy_volumes = await _load_day_volumes(db, rdate, held_tickers)
            sell_volumes = await _load_day_volumes(db, sell_date, held_tickers)
            # 成交量为 0 → 停牌/不可交易（涨跌停未单独建模）
            buy_prices = {t: p for t, p in buy_prices.items() if (buy_volumes.get(t) or 0) > 0}
            sell_prices = {t: p for t, p in sell_prices.items() if (sell_volumes.get(t) or 0) > 0}
            cost_buy = settings.BACKTEST_COMMISSION_RATE + settings.BACKTEST_SLIPPAGE_RATE
            cost_sell = (
                settings.BACKTEST_COMMISSION_RATE
                + settings.BACKTEST_STAMP_DUTY_RATE
                + settings.BACKTEST_SLIPPAGE_RATE
            )
            holdings = backtest.compute_holding_returns(
                portfolio,
                buy_prices,
                sell_prices,
                cost_buy=cost_buy,
                cost_sell=cost_sell,
            )
            period_ret = sum(h["return"] for h in holdings) / len(holdings)

            # 基准同期收益（bench 在循环外已拉取一次，此处复用）
            bench_ret = _bench_return(bench, rdate, sell_date)

            periods_result.append(
                {
                    "year": rdate.year,
                    "rebalance_date": rdate.isoformat(),
                    "return": period_ret,
                    "bench": bench_ret,
                    "holdings": [
                        {k: h[k] for k in ("ticker", "name", "buy", "sell", "return", "suspended")}
                        for h in holdings
                    ],
                }
            )

        # ⑤ 汇总 + 落库（设计约定形状：{"summary": {...}, "yearly": [...]})
        stats = backtest.compute_nav_and_stats(
            periods_result, risk_free_rate=settings.BACKTEST_RISK_FREE_RATE
        )
        result = {
            "summary": {k: v for k, v in stats.items() if k != "yearly"},
            "yearly": stats["yearly"],
        }
        result["preset_name"] = preset.name
        result["start"] = start.isoformat()
        result["end"] = end.isoformat()
        result["disclaimers"] = [
            (
                f"已计交易费用：佣金 {settings.BACKTEST_COMMISSION_RATE:.2%}、"
                f"卖出印花税 {settings.BACKTEST_STAMP_DUTY_RATE:.2%}、"
                f"单边滑点 {settings.BACKTEST_SLIPPAGE_RATE:.2%}"
            ),
            "停牌（成交量为 0）按不可交易处理；涨跌停不可交易未单独建模",
            "市值为近似值：调仓日收盘价 × 当前总股本",
            "存在幸存者偏差：已退市股票可能不在数据源中",
            "财务可见性：有公告日的指标按公告日过滤；缺失公告日的按披露截止日近似",
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
            source="screener",
            event_type="backtest.completed",
            entity_type="backtest_run",
            entity_id=str(run.id),
            summary=(
                f"回测完成：{preset.name} {run.years}年，"
                f"{result['summary']['periods_count']} 期，"
                f"累计 {result['summary']['total_return']:.1%}"
            ),
        )
    except Exception as e:  # noqa: BLE001 — 全链路兜底：失败要可见
        run.status = "failed"
        run.error = str(e)
        run.finished_at = _now_iso()
        logger.exception("回测失败 %s", run_id)
        await EventLogger(db).record(
            source="screener",
            event_type="backtest.failed",
            entity_type="backtest_run",
            entity_id=str(run.id),
            summary=str(e)[:500],
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
