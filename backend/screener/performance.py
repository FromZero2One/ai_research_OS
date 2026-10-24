"""推荐后表现 — 基于 T+1 收盘买入的等权收益跟踪（纯函数可单测）。"""

from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta

HORIZONS: dict[str, int] = {"1m": 30, "3m": 90, "6m": 180, "12m": 365}


def _price_on_or_after(
    dates: list[date], prices: list[float], target: date
) -> float | None:
    idx = bisect_left(dates, target)
    return prices[idx] if idx < len(prices) else None


def compute_stock_performance(
    entry_date: date,
    entry_price: float | None,
    price_rows: list[tuple[date, float]],
) -> dict:
    """单只推荐股在各期限的收益；price_rows 为 entry_date 之后（含）的日线。

    收益 = 期限目标日（或之后首个交易日）收盘 / 买入价 - 1。
    尚未到达期限、或目标日之后没有价格 → None。
    """
    dates = [d for d, _ in price_rows]
    prices = [p for _, p in price_rows]
    out: dict = {
        "entry_date": entry_date.isoformat() if entry_date else None,
        "entry_price": entry_price,
        "current_return": None,
        "horizons": {key: None for key in HORIZONS},
    }
    if entry_price is None or entry_price <= 0 or not price_rows:
        return out

    out["current_return"] = prices[-1] / entry_price - 1.0
    for key, days in HORIZONS.items():
        target = entry_date + timedelta(days=days)
        price = _price_on_or_after(dates, prices, target)
        if price is not None:
            out["horizons"][key] = price / entry_price - 1.0
    return out


def summarize(rows: list[dict]) -> dict:
    """等权汇总各期限收益：平均、胜率、样本数。"""
    summary: dict = {}
    for key in HORIZONS:
        values = [
            r["horizons"][key]
            for r in rows
            if r.get("horizons", {}).get(key) is not None
        ]
        summary[key] = _stats(values)
    summary["current"] = _stats(
        [r["current_return"] for r in rows if r.get("current_return") is not None]
    )
    return summary


def _stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "avg_return": None, "hit_rate": None}
    return {
        "count": len(values),
        "avg_return": sum(values) / len(values),
        "hit_rate": sum(1 for v in values if v > 0) / len(values),
    }
