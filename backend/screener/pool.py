"""股票池过滤 — 板块归属映射 + 按规则过滤全市场快照（纯函数）。"""

from __future__ import annotations


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
) -> list[dict]:
    """按股票池声明过滤全市场快照。

    spot 项结构：{ticker, name, price, turnover, market_cap}；
    pool 为 rules.stock_pool（type + 可选 tickers）；
    watchlist 池 = 自选公司（watched_tickers）∪ 文档内列出的 tickers，文档声明优先。
    """
    pool_type = pool.get("type", "all")
    extra = set(pool.get("tickers") or [])

    out: list[dict] = []
    for item in spot:
        board = board_of(item["ticker"])
        if board is None:
            continue  # 非 A 股前缀直接排除
        if pool_type == "all":
            out.append(item)
        elif pool_type == "watchlist":
            if item["ticker"] in watched_tickers or item["ticker"] in extra:
                out.append(item)
        elif board == pool_type:
            out.append(item)
    return out
