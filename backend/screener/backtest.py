"""回测核心 — 纯函数（调仓日生成、财务期选择、组合收益、净值指标）。

无 IO、无 LLM。确定性可单测；数据准备见 backtest_data.py。
口径（spec 2026-10-23）：
- 4 月调仓统一用上一年年报（Q4），不混用当年 Q1
- 收益一律前复权 close
- 停牌（卖出价缺失）→ 收益 0 + suspended 标注
- 最大回撤按调仓日净值序列（MVP 简化）
"""

from __future__ import annotations

import datetime as dt

# 报告期 → 披露完成截止日（Q4 年报为次年 4-30）
_DISCLOSURE_DEADLINE = {
    "Q1": (4, 30),     # 当年 4-30
    "Q2": (8, 31),     # 当年 8-31
    "Q3": (10, 31),    # 当年 10-31
    "Q4": (4, 30),     # 次年 4-30
}


def build_disclosure_map(start_year: int = 1995, end_year: int = 2030) -> dict[tuple[int, str], dt.date]:
    """报告期 (year, period) → 披露截止日。"""
    m: dict[tuple[int, str], dt.date] = {}
    for year in range(start_year, end_year):
        for period, (month, day) in _DISCLOSURE_DEADLINE.items():
            reveal_year = year + 1 if period == "Q4" else year
            m[(year, period)] = dt.date(reveal_year, month, day)
    return m


def pick_financial_period(asof: dt.date) -> tuple[int, str]:
    """asof 日前最近一个**已完整披露**的报告期。

    4-30~8-30 窗口用上一年 Q4（年报优先于当年 Q1，spec 决策）。
    无已披露报告期（asof 太早）→ ValueError。
    """
    m = build_disclosure_map()
    candidates = [(d, yp) for yp, d in m.items() if d <= asof]
    if not candidates:
        raise ValueError(f"调仓日 {asof} 之前无任何已披露报告期")
    return max(candidates, key=lambda x: x[0])[1]


def generate_rebalance_dates(
    price_dates: list[dt.date], start: dt.date, end: dt.date
) -> list[dt.date]:
    """每个披露截止日（落在区间内）后的首个交易日，升序去重。

    price_dates 为空 → ValueError("无价格日历")，不产出退化回测。
    """
    if not price_dates:
        raise ValueError("无价格日历")
    sorted_days = sorted(set(price_dates))
    m = build_disclosure_map()
    cutoffs = sorted({d for d in m.values() if start <= d <= end})
    out: list[dt.date] = []
    for cutoff in cutoffs:
        first = next((d for d in sorted_days if d > cutoff), None)
        if first is not None and first not in out:
            out.append(first)
    return sorted(out)


def select_portfolio(
    rebalance_date: dt.date,
    preset_rules: list[dict],
    snapshot_rows: list[dict],
    financials_by_ticker: dict[str, list],
    limit: int = 20,
) -> tuple[list[dict], list[dict]]:
    """单期选股：调用量化规则求值 + 排名截断（复用 screening 纯函数）。

    snapshot_rows 为该调仓日的价格行（含近似 market_cap）。
    返回 (入选组合, 因缺数据被排除者)。
    """
    from screener.screening import evaluate_quant_rules, rank_candidates

    passed, excluded = evaluate_quant_rules(snapshot_rows, preset_rules, financials_by_ticker)
    ranked = rank_candidates(passed, limit=limit)
    return ranked, excluded


def compute_holding_returns(
    portfolio: list[dict],
    buy_prices: dict[str, float],
    sell_prices: dict[str, float],
) -> list[dict]:
    """组合各票买入→卖出的持有期收益。卖出价缺失（停牌）→ 0 + suspended。"""
    out = []
    for cand in portfolio:
        ticker = cand["ticker"]
        buy = buy_prices.get(ticker)
        sell = sell_prices.get(ticker)
        if buy is None:
            return_row = 0.0
            suspended = True
        elif sell is None:
            return_row = 0.0
            suspended = True
        else:
            return_row = sell / buy - 1.0
            suspended = False
        out.append({**cand, "buy": buy, "sell": sell, "return": return_row, "suspended": suspended})
    return out


def compute_nav_and_stats(periods: list[dict]) -> dict:
    """调仓期收益序列 → 汇总指标 + 逐年明细。

    periods 每项含 year/rebalance_date/return/bench/holdings。
    """
    nav = 1.0
    bench_nav = 1.0
    peak = 1.0
    max_dd = 0.0
    yearly: list[dict] = []
    for p in periods:
        nav *= 1.0 + p["return"]
        bench_nav *= 1.0 + p["bench"]
        peak = max(peak, nav)
        if peak > 0:
            max_dd = min(max_dd, nav / peak - 1.0)
        yearly.append({
            "year": p["year"],
            "rebalance_date": p["rebalance_date"],
            "return": p["return"],
            "bench": p["bench"],
            "excess": p["return"] - p["bench"],
            "nav": nav,
            "holdings": p.get("holdings", []),
        })

    n = len(periods)
    total_return = nav - 1.0
    bench_total = bench_nav - 1.0
    # CAGR：每期约一个季度 → 年化 = nav^(4/n) - 1
    cagr = nav ** (4.0 / n) - 1.0 if n > 0 and nav > 0 else 0.0
    wins = sum(1 for y in yearly if y["excess"] > 0)
    return {
        "total_return": total_return,
        "bench_total_return": bench_total,
        "cagr": cagr,
        "max_drawdown": max_dd,
        "win_rate": wins / n if n else 0.0,
        "periods_count": n,
        "yearly": yearly,
    }
