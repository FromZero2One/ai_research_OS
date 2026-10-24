"""组合构建 — 推荐股 → 资金分配（等权/得分/置信度加权 + 单票/行业上限）。

约束冲突时保留现金，不做杠杆；返回的权重合计 ≤ 1。
"""

from __future__ import annotations


def _basis(candidate: dict, method: str) -> float:
    if method == "equal":
        return 1.0
    if method == "score":
        return max(float(candidate.get("score") or 0.0), 1e-9)
    if method == "confidence":
        return max(float(candidate.get("confidence") or 0.0), 1e-9)
    raise ValueError(f"未知权重方式: {method!r}")


def construct_portfolio(
    candidates: list[dict],
    capital: float = 1_000_000.0,
    method: str = "equal",
    max_weight: float = 0.15,
    max_industry_weight: float = 0.35,
    max_holdings: int = 20,
) -> dict:
    """按约束分配资金。candidates 需含 ticker/name/industry/score/confidence/price。"""
    if capital <= 0:
        raise ValueError("capital 必须大于 0")
    if not (0 < max_weight <= 1):
        raise ValueError("max_weight 必须在 (0, 1]")
    if not (0 < max_industry_weight <= 1):
        raise ValueError("max_industry_weight 必须在 (0, 1]")
    if not (1 <= max_holdings <= 200):
        raise ValueError("max_holdings 必须在 1-200")

    valid = [c for c in candidates if c.get("ticker")]
    ranked = sorted(
        valid,
        key=lambda c: (
            _basis(c, method),
            float(c.get("score") or 0.0),
            str(c.get("ticker")),
        ),
        reverse=True,
    )[:max_holdings]
    if not ranked:
        return {
            "method": method, "capital": capital, "invested": 0.0,
            "cash": capital, "cash_weight": 1.0, "holdings": [],
            "warnings": ["没有推荐股票，全部保留现金"],
        }

    by_ticker = {c["ticker"]: c for c in ranked}
    industry_of = {
        c["ticker"]: (c.get("industry") or "未知") for c in ranked
    }
    total_basis = sum(_basis(c, method) for c in ranked)
    weights = {c["ticker"]: _basis(c, method) / total_basis for c in ranked}

    # 单票 + 行业上限：只向下收缩，剩余留现金（不做杠杆）
    for _ in range(50):
        changed = False
        for ticker, weight in list(weights.items()):
            if weight > max_weight + 1e-12:
                weights[ticker] = max_weight
                changed = True

        industry_sums: dict[str, float] = {}
        for ticker, weight in weights.items():
            industry = industry_of[ticker]
            industry_sums[industry] = industry_sums.get(industry, 0.0) + weight
        for industry, total in industry_sums.items():
            if total > max_industry_weight + 1e-12:
                scale = max_industry_weight / total
                for ticker, weight in list(weights.items()):
                    if industry_of[ticker] == industry:
                        weights[ticker] = weight * scale
                changed = True

        if not changed:
            break

    invested_weight = min(1.0, sum(weights.values()))
    cash_weight = max(0.0, 1.0 - invested_weight)
    holdings = []
    for ticker, weight in sorted(weights.items(), key=lambda kv: kv[1], reverse=True):
        cand = by_ticker[ticker]
        holdings.append(
            {
                "ticker": ticker,
                "name": cand.get("name"),
                "industry": industry_of[ticker],
                "price": cand.get("price"),
                "score": cand.get("score"),
                "confidence": cand.get("confidence"),
                "weight": weight,
                "amount": capital * weight,
            }
        )

    warnings: list[str] = []
    if len(valid) > len(ranked):
        warnings.append(
            f"按 max_holdings={max_holdings} 截断，"
            f"未纳入 {len(valid) - len(ranked)} 只"
        )
    if cash_weight > 0.01:
        warnings.append(f"单票/行业上限约束下保留现金 {cash_weight:.1%}")
    return {
        "method": method,
        "capital": capital,
        "invested": capital * invested_weight,
        "cash": capital * cash_weight,
        "cash_weight": cash_weight,
        "holdings": holdings,
        "warnings": warnings,
    }
