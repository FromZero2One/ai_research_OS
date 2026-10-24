"""已保存组合的再平衡计算（纯函数）。

口径：
- 用保存时的金额/价格推算股数，按最新收盘价估算当前市值；
- 目标权重沿用保存时的权重（不做新一轮选股）；
- 漂移在 tolerance 内视为持有；买入股数按 lot_size 向下取整，卖出可按实际股数；
- 缺最新价时回退保存价并标记 stale_price。
"""

from __future__ import annotations

from typing import Any


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def compute_rebalance(
    holdings: list[dict],
    current_prices: dict[str, float],
    cash: float = 0.0,
    tolerance: float = 0.01,
    lot_size: int = 100,
) -> dict:
    """返回当前权重/漂移/买卖建议。"""
    lot_size = max(1, int(lot_size))
    tolerance = max(0.0, float(tolerance))
    cash = _num(cash)

    rows: list[dict] = []
    total_value = cash
    for h in holdings:
        entry_price = _num(h.get("price"))
        amount = _num(h.get("amount"))
        price = current_prices.get(h.get("ticker"))
        stale = price is None or price <= 0
        price = entry_price if stale else float(price)
        shares = amount / entry_price if entry_price > 0 else 0.0
        value = shares * price
        total_value += value
        rows.append(
            {
                "ticker": h.get("ticker"),
                "name": h.get("name"),
                "industry": h.get("industry"),
                "entry_price": entry_price or None,
                "current_price": price or None,
                "shares": round(shares, 2),
                "current_value": value,
                "target_weight": _num(h.get("weight")),
                "stale_price": stale,
            }
        )

    if total_value <= 0:
        for row in rows:
            row.update(
                current_weight=0.0, drift=0.0, action="hold",
                amount_delta=0.0, shares_delta=0, lot_blocked=False,
            )
        return {
            "total_value": 0.0,
            "invested_value": 0.0,
            "cash": cash,
            "cash_weight": 0.0,
            "tolerance": tolerance,
            "lot_size": lot_size,
            "holdings": rows,
            "summary": {"buys": 0, "sells": 0, "holds": len(rows)},
        }

    buys = sells = holds = 0
    for row in rows:
        weight = row["current_value"] / total_value
        target_value = row["target_weight"] * total_value
        delta = target_value - row["current_value"]
        drift = weight - row["target_weight"]
        price = row["current_price"] or 0.0
        lot_blocked = False
        if row["stale_price"]:
            # 缺最新价时不基于旧价给交易建议
            action, amount_delta, shares_delta = "hold", 0.0, 0
            holds += 1
        elif abs(drift) <= tolerance or price <= 0:
            action, amount_delta, shares_delta = "hold", 0.0, 0
            holds += 1
        elif delta > 0:
            shares_delta = int((delta / price) // lot_size) * lot_size
            if shares_delta == 0:
                # 目标增量不足一手：不强行交易
                action, amount_delta = "hold", 0.0
                lot_blocked = True
                holds += 1
            else:
                action = "buy"
                amount_delta = shares_delta * price
                buys += 1
        else:
            shares_delta = int(delta / price)  # 卖出可为任意股数
            action = "sell"
            amount_delta = shares_delta * price
            sells += 1
        row.update(
            current_weight=weight,
            drift=drift,
            action=action,
            amount_delta=amount_delta,
            shares_delta=shares_delta,
            lot_blocked=lot_blocked,
        )

    invested = sum(r["current_value"] for r in rows)
    return {
        "total_value": total_value,
        "invested_value": invested,
        "cash": cash,
        "cash_weight": cash / total_value,
        "tolerance": tolerance,
        "lot_size": lot_size,
        "holdings": rows,
        "summary": {"buys": buys, "sells": sells, "holds": holds},
    }
