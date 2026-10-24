"""行业相对排名 — 候选在其所属行业内的分位与综合行业得分（纯函数）。

金融行业用 PE/PB/ROE；工业行业额外看成长与现金流质量。
分位 1.0 = 行业内最好；PE/PB 越低越好（已反转）。
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict

from screener.screening import _metric_value
from screener.valuation import derive_quality, derive_valuation

INDUSTRIAL_RANK_METRICS = (
    "roe", "revenue_growth", "net_income_growth", "cfo_to_ni", "pe", "pb",
)
FINANCIAL_RANK_METRICS = ("pb", "pe", "roe")
LOWER_IS_BETTER = frozenset({"pe", "pb"})


def _metric_values(candidate: dict, entries: list, metrics: tuple[str, ...]) -> dict:
    quality = derive_quality(entries)
    valuation = derive_valuation(candidate, entries)
    values: dict[str, float] = {}
    for metric in metrics:
        if metric == "cfo_to_ni":
            value = quality.get(metric)
        elif metric in ("pe", "pb"):
            value = valuation.get(metric)
        else:
            value = _metric_value(entries, metric)
        if value is not None:
            values[metric] = float(value)
    return values


def _percentile(value: float, values: list[float], higher_better: bool) -> float:
    """行业内分位；样本 <3 返回 0.5 中性。"""
    if len(values) < 3:
        return 0.5
    ordered = sorted(values)
    rank = bisect_left(ordered, value) / (len(ordered) - 1)
    return rank if higher_better else 1.0 - rank


def compute_industry_percentiles(
    pool: list[dict],
    financials_by_ticker: dict[str, list],
) -> dict[str, dict]:
    """返回 {ticker: {"industry_percentiles": {...}, "industry_score": float}}。"""
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    values_by_ticker: dict[str, dict[str, float]] = {}

    for cand in pool:
        sector = cand.get("sector") or "industrial"
        metrics = FINANCIAL_RANK_METRICS if sector == "financial" else INDUSTRIAL_RANK_METRICS
        values = _metric_values(
            cand, financials_by_ticker.get(cand["ticker"], []), metrics
        )
        values_by_ticker[cand["ticker"]] = values
        industry = cand.get("industry") or "未知"
        for metric, value in values.items():
            grouped[industry][metric].append(value)

    result: dict[str, dict] = {}
    for cand in pool:
        industry = cand.get("industry") or "未知"
        values = values_by_ticker.get(cand["ticker"], {})
        percentiles = {
            metric: _percentile(
                value,
                grouped[industry][metric],
                higher_better=metric not in LOWER_IS_BETTER,
            )
            for metric, value in values.items()
        }
        score = sum(percentiles.values()) / len(percentiles) if percentiles else 0.5
        result[cand["ticker"]] = {
            "industry_percentiles": percentiles,
            "industry_score": score,
        }
    return result
