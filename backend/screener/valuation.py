"""估值指标派生 — 快照市值 + 最新报告期财务数据（纯函数，零额外数据源）。

为什么不直接用 market.valuation_history：该表按需逐只拉取、当前覆盖为 0，
无法支撑全市场选股。这里用全市场已有的 market_cap + 财务三表即时派生：

- PE = 总市值 / 年化净利润（净利润 <= 0 → 无意义，返回 None）
- PS = 总市值 / 年化营业收入（营收 <= 0 → None）
- PB = 总市值 / (总资产 - 总负债)（净资产 <= 0 → None）

季报利润/营收是年初至今累计值，需按报告期年化（Q1×4、Q2×2、Q3×4/3、
Q4/年报×1），因此 PE/PS 是「年化近似值」，报告与指标库均已标注。
"""

from __future__ import annotations

from market.domain import FinancialMetricEntry

VALUATION_METRICS: frozenset[str] = frozenset({"pe", "pb", "ps"})
VALUATION_INPUTS: frozenset[str] = frozenset(
    {"net_income", "revenue", "total_assets", "total_liabilities"}
)
_VALUATION_INPUT_MAP: dict[str, frozenset[str]] = {
    "pe": frozenset({"net_income"}),
    "pb": frozenset({"total_assets", "total_liabilities"}),
    "ps": frozenset({"revenue"}),
}

_PERIOD_RANK = {"Q1": 1, "Q2": 2, "Semi": 2, "Q3": 3, "Q4": 4, "Annual": 4}
_PERIOD_ANNUALIZE = {1: 4.0, 2: 2.0, 3: 4.0 / 3.0, 4: 1.0}


def annualization_factor(period: str | None) -> float:
    """年初至今累计值 → 年化值的乘数。未知期次按年报处理（×1）。"""
    return _PERIOD_ANNUALIZE.get(_PERIOD_RANK.get(period or "", 4), 1.0)


def _metric_latest(
    entries: list[FinancialMetricEntry], metric: str
) -> tuple[float | None, str | None]:
    """返回 (最新值, 该值所属期次)。同 metric 多期时按 (year, period) 取最大。"""
    best: tuple[tuple[int, int], float, str] | None = None
    for entry in entries:
        if entry.metric_name != metric or entry.metric_value is None:
            continue
        key = (entry.fiscal_year, _PERIOD_RANK.get(entry.fiscal_period, 0))
        if best is None or key > best[0]:
            best = (key, entry.metric_value, entry.fiscal_period)
    return (best[1], best[2]) if best else (None, None)


def _latest_period(entries: list[FinancialMetricEntry]) -> str | None:
    best: tuple[tuple[int, int], str] | None = None
    for entry in entries:
        key = (entry.fiscal_year, _PERIOD_RANK.get(entry.fiscal_period, 0))
        if best is None or key > best[0]:
            best = (key, entry.fiscal_period)
    return best[1] if best else None


def derive_valuation(
    candidate: dict, financials: list[FinancialMetricEntry]
) -> dict[str, float | None]:
    """从快照 + 最新财务数据派生 PE/PB/PS。缺数据或分母非正 → None。"""
    result: dict[str, float | None] = {metric: None for metric in VALUATION_METRICS}
    try:
        market_cap = float(candidate.get("market_cap"))
    except (TypeError, ValueError):
        return result
    if market_cap <= 0:
        return result

    net_income, ni_period = _metric_latest(financials, "net_income")
    revenue, rev_period = _metric_latest(financials, "revenue")
    assets, _ = _metric_latest(financials, "total_assets")
    liabilities, _ = _metric_latest(financials, "total_liabilities")
    default_period = _latest_period(financials)

    if net_income is not None and net_income > 0:
        factor = annualization_factor(ni_period or default_period)
        result["pe"] = market_cap / (net_income * factor)
    if revenue is not None and revenue > 0:
        factor = annualization_factor(rev_period or default_period)
        result["ps"] = market_cap / (revenue * factor)
    if assets is not None and liabilities is not None:
        equity = assets - liabilities
        if equity > 0:
            result["pb"] = market_cap / equity
    return result


def required_data_metrics(rule_metrics: set[str]) -> set[str]:
    """规则里出现估值指标时，精确追加计算它们所需的底层财务指标。"""
    metrics = set(rule_metrics)
    extra: set[str] = set()
    for metric in metrics & VALUATION_METRICS:
        extra |= _VALUATION_INPUT_MAP[metric]
    return (metrics - VALUATION_METRICS) | extra
