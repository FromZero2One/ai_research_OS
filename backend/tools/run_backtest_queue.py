"""回测脚本 — 按预设顺序直调回测纯函数，逐个落 JSON 报告（已去框架化）。

回测不再走任务队列 / run 状态机：本脚本直调 `screener.backtest` 纯函数 +
`screener.backtest_data` 拉数，结果 dict 原样 json.dump 到
`screener/reports/backtest-{preset}-{YYYYMMDD}.json`。

用法（cd backend）：
    .venv\\Scripts\\python tools\\run_backtest_queue.py
前置：
- docker 依赖栈运行中（docker compose -f docker/docker-compose.yml up -d）
- .env 配置 BACKTEST_MYSQL_URL（外部 MySQL 前复权日线）
- 可用 BACKTEST_YEARS 覆盖回测年数（默认 3）
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from core.config import settings  # noqa: E402
from core.database import managed_session  # noqa: E402
from core.logging import logger  # noqa: E402
from screener import backtest, backtest_data  # noqa: E402
from screener.models import CriteriaPreset  # noqa: E402

PRESET_NAMES = [
    "深度价值",
    "核心资产",
    "高成长",
    "GARP",
    "周期反转",
    "金融价值",
]
YEARS = int(os.getenv("BACKTEST_YEARS", "3"))
REPORT_DIR = Path(__file__).resolve().parent.parent / "screener" / "reports"


async def run_preset_backtest(db, preset: CriteriaPreset) -> dict:
    """单个预设的回测全流程（口径与原回测编排一致，无 run 落库）。"""
    end = dt.date.today()
    start = end.replace(year=end.year - YEARS)

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
        logger.info("活跃公司票池过小（%d 只），改用全市场票池：%d 只", len(active), len(market))
    # 逐只拉取并立即落库（拉一只灌一只，本地库行数即进度，中断可续）
    synced_tickers = await backtest_data.fetch_daily_from_mysql(db, sorted(tickers), start, end)
    if synced_tickers == 0 and not await backtest_data._price_dates_from_pg(db, start, end):
        raise ValueError("外部日线数据为空（BACKTEST_MYSQL_URL 或外部库不可用）")
    await db.flush()
    logger.info("回测日线本次落库 %d 只", synced_tickers)

    price_dates = await backtest_data._price_dates_from_pg(db, start, end)
    if not price_dates:
        raise ValueError("无价格日历（灌库后仍为空）")
    rebalance_dates = backtest.generate_rebalance_dates(price_dates, start, end)

    # ② 历史财务：各调仓日前最近已披露报告期（年报口径）+ PIT 公告日过滤
    periods = sorted({backtest.pick_financial_period(d) for d in rebalance_dates})
    await backtest_data.ensure_financial_periods(db, periods)
    asof_by_period: dict[tuple[int, str], dt.date] = {}
    for d in rebalance_dates:
        fp = backtest.pick_financial_period(d)
        asof_by_period[fp] = min(asof_by_period.get(fp, d), d)
    financials_by_period = await backtest_data._load_financials_by_period(
        db, periods, asof_by_period
    )

    # ③ 近似市值用的当前总股本
    all_tickers = sorted(tickers)
    shares = await backtest_data._fetch_total_shares(db, all_tickers)

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
    bench = await backtest_data.fetch_index_daily(start, end)

    # ④ 逐调仓期：选股 → 买入/卖出结算 → 期收益
    periods_result: list[dict] = []
    for i, rdate in enumerate(rebalance_dates):
        fp = backtest.pick_financial_period(rdate)
        fin = financials_by_period.get(fp, {})

        # 当日快照行：价格 + 近似市值（收盘价 × 当前总股本）
        closes = await backtest_data._load_day_closes(db, rdate, all_tickers)
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
        buy_prices = await backtest_data._load_day_closes(db, rdate, held_tickers)
        sell_prices = await backtest_data._load_day_closes(db, sell_date, held_tickers)
        buy_volumes = await backtest_data._load_day_volumes(db, rdate, held_tickers)
        sell_volumes = await backtest_data._load_day_volumes(db, sell_date, held_tickers)
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
        bench_ret = backtest_data._bench_return(bench, rdate, sell_date)

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

    # ⑤ 汇总（{"summary": {...}, "yearly": [...]}，原样落盘）
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
    return result


async def main() -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.date.today().strftime("%Y%m%d")
    async with managed_session() as db:
        for name in PRESET_NAMES:
            preset = (
                await db.execute(select(CriteriaPreset).where(CriteriaPreset.name == name).limit(1))
            ).scalar_one_or_none()
            if preset is None:
                print(f"[{name}] 预设不存在，跳过", flush=True)
                continue
            print(f"[{name}] 开始回测（{YEARS} 年）…", flush=True)
            try:
                result = await run_preset_backtest(db, preset)
                await db.commit()
            except Exception as e:  # noqa: BLE001 — 单预设失败不阻塞后续预设
                await db.rollback()
                print(f"[{name}] 失败: {e}", flush=True)
                logger.exception("回测失败 %s", name)
                continue
            path = REPORT_DIR / f"backtest-{name}-{stamp}.json"
            path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            s = result["summary"]
            print(
                f"[{name}] 完成 → {path.name} | CAGR={s.get('cagr')} "
                f"基准CAGR={s.get('bench_cagr')} 超额={s.get('excess_cagr')} "
                f"Sharpe={s.get('sharpe')} 最大回撤={s.get('max_drawdown')}",
                flush=True,
            )
    print("=== 回测脚本完成 ===", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
