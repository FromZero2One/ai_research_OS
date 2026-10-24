"""股票池过滤 — 板块归属映射 + 按规则过滤全市场快照（纯函数）。

入口处统一做风险卫生过滤：ST/*ST/退市、停牌/无行情、低流动性、小市值。
这些是投资决策的硬约束，不应由每个预设重复配置。
"""

from __future__ import annotations

import re

from core.config import settings

_HYGIENE_KEYS = ("st", "suspended", "low_liquidity", "small_cap", "non_a")


def _is_st_or_delisting(name: str) -> bool:
    text = str(name or "")
    return bool(re.search(r"(^|\*)ST", text, re.IGNORECASE)) or "退" in text


def _hygiene_reason(item: dict) -> str | None:
    """返回首个不通过原因；通过返回 None。"""
    if _is_st_or_delisting(item.get("name", "")):
        return "st"
    price = item.get("price")
    turnover = item.get("turnover")
    market_cap = item.get("market_cap")
    if (
        price is None
        or float(price) <= 0
        or turnover is None
        or float(turnover) <= 0
        or market_cap is None
        or float(market_cap) <= 0
    ):
        return "suspended"
    if float(turnover) < settings.SCREENER_MIN_TURNOVER:
        return "low_liquidity"
    if float(market_cap) < settings.SCREENER_MIN_MARKET_CAP:
        return "small_cap"
    return None


def board_of(ticker: str) -> str | None:
    """A 股板块归属：main（沪/深主板）/ chinext（创业板）/ star（科创板），非 A 股 None。"""
    t = ticker.strip()
    if len(t) == 6 and t.isdigit():
        if t.startswith(("60", "00")):
            return "main"
        if t.startswith("3"):
            return "chinext"
        if t.startswith("68"):
            return "star"
    return None


def filter_pool(
    spot: list[dict],
    pool: dict,
    watched_tickers: set[str],
    excluded_out: dict[str, int] | None = None,
) -> list[dict]:
    """按股票池声明过滤全市场快照（先做风险卫生，再做板块/自选过滤）。

    spot 项结构：{ticker, name, price, turnover, market_cap}；
    pool 为 rules.stock_pool（type + 可选 tickers）；
    watchlist 池 = 自选公司（watched_tickers）∪ 文档内列出的 tickers，文档声明优先。
    excluded_out 可选，用于统计各原因排除数量（报告展示）。
    """
    pool_type = pool.get("type", "all")
    extra = set(pool.get("tickers") or [])
    stats = excluded_out if excluded_out is not None else {}
    for key in _HYGIENE_KEYS:
        stats.setdefault(key, 0)

    out: list[dict] = []
    for item in spot:
        board = board_of(item["ticker"])
        if board is None:
            stats["non_a"] += 1
            continue  # 非 A 股前缀直接排除

        reason = _hygiene_reason(item)
        if reason:
            stats[reason] += 1
            continue

        if pool_type == "all":
            out.append(item)
        elif pool_type == "watchlist":
            if item["ticker"] in watched_tickers or item["ticker"] in extra:
                out.append(item)
        elif board == pool_type:
            out.append(item)
    return out
