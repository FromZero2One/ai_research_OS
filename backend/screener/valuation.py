"""估值与盈利质量派生指标 — 快照市值 + 财务数据（纯函数，零额外数据源）。

估值：
- PE(年化/TTM) = 总市值 / 净利润（TTM 优先；缺历史期时回退单期年化）
- PS(年化/TTM) = 总市值 / 营业收入
- PB = 总市值 / (总资产 - 总负债)

盈利质量：
- cfo_to_ni = TTM 经营现金流 / TTM 净利润（倍）
- cfo_to_revenue = TTM 经营现金流 / TTM 营业收入（%）
- accrual_ratio = (TTM 净利润 - TTM 经营现金流) / 最新总资产（%）

TTM 公式：最新年报 + 本期累计 − 上年同期累计。
例：2026Q2 TTM = FY2025 + 2026H1 − 2025H1。
若历史期缺失，回退到「本期累计 × 年化系数」，并在报告中按现有口径展示。
"""

from __future__ import annotations

from market.domain import FinancialMetricEntry

VALUATION_METRICS: frozenset[str] = frozenset(
    {"pe", "pb", "ps", "peg", "fcf_yield"}
)
VALUATION_INPUTS: frozenset[str] = frozenset(
    {
        "net_income", "revenue", "total_assets", "total_liabilities",
        "net_income_growth", "fcff",
    }
)
QUALITY_METRICS: frozenset[str] = frozenset(
    {"cfo_to_ni", "cfo_to_revenue", "accrual_ratio"}
)
QUALITY_INPUTS: frozenset[str] = frozenset(
    {"operating_cash_flow", "net_income", "revenue", "total_assets"}
)
BANK_METRICS: frozenset[str] = frozenset({"npl_ratio"})
BANK_INPUTS: frozenset[str] = frozenset({"non_performing_loan", "gross_loans"})

_VALUATION_INPUT_MAP: dict[str, frozenset[str]] = {
    "pe": frozenset({"net_income"}),
    "pb": frozenset({"total_assets", "total_liabilities"}),
    "ps": frozenset({"revenue"}),
    "peg": frozenset({"net_income", "net_income_growth"}),
    "fcf_yield": frozenset({"fcff"}),
}
_QUALITY_INPUT_MAP: dict[str, frozenset[str]] = {
    "cfo_to_ni": frozenset({"operating_cash_flow", "net_income"}),
    "cfo_to_revenue": frozenset({"operating_cash_flow", "revenue"}),
    "accrual_ratio": frozenset(
        {"operating_cash_flow", "net_income", "total_assets"}
    ),
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


def _period_values(
    entries: list[FinancialMetricEntry], metric: str
) -> dict[tuple[int, str], float]:
    values: dict[tuple[int, str], float] = {}
    for entry in entries:
        if entry.metric_name != metric or entry.metric_value is None:
            continue
        values[(entry.fiscal_year, entry.fiscal_period)] = entry.metric_value
    return values


def ttm_value(
    entries: list[FinancialMetricEntry], metric: str
) -> tuple[float | None, bool]:
    """返回 (值, 是否为严格 TTM)。

    年报直接作为 TTM；季报用「上年年报 + 本期累计 − 上年同期」；历史期缺失
    时回退到单期年化（is_ttm=False）。无数据返回 (None, False)。
    """
    values = _period_values(entries, metric)
    if not values:
        return (None, False)

    latest_key = max(values, key=lambda k: (k[0], _PERIOD_RANK.get(k[1], 0)))
    year, period = latest_key
    rank = _PERIOD_RANK.get(period, 0)
    current = values[latest_key]
    if rank == 4:
        return (current, True)

    prev_same = values.get((year - 1, period))
    prev_annual = values.get((year - 1, "Q4")) or values.get((year - 1, "Annual"))
    if prev_same is not None and prev_annual is not None:
        return (prev_annual + current - prev_same, True)

    # 历史期缺失：保留旧口径（单期年化），避免整个指标不可用
    return (current * annualization_factor(period), False)


def derive_valuation(
    candidate: dict, financials: list[FinancialMetricEntry]
) -> dict[str, float | None]:
    """从快照 + 财务派生 PE/PB/PS。PE/PS 优先 TTM，缺历史期回退年化。"""
    result: dict[str, float | None] = {metric: None for metric in VALUATION_METRICS}
    try:
        market_cap = float(candidate.get("market_cap"))
    except (TypeError, ValueError):
        return result
    if market_cap <= 0:
        return result

    net_income, _ = ttm_value(financials, "net_income")
    revenue, _ = ttm_value(financials, "revenue")
    assets, _ = _metric_latest(financials, "total_assets")
    liabilities, _ = _metric_latest(financials, "total_liabilities")

    if net_income is not None and net_income > 0:
        result["pe"] = market_cap / net_income
    if revenue is not None and revenue > 0:
        result["ps"] = market_cap / revenue
    if assets is not None and liabilities is not None:
        equity = assets - liabilities
        if equity > 0:
            result["pb"] = market_cap / equity

    growth, _ = _metric_latest(financials, "net_income_growth")
    if result["pe"] is not None and growth is not None and growth > 0:
        result["peg"] = result["pe"] / growth

    fcff, _ = _metric_latest(financials, "fcff")
    if fcff is not None:
        result["fcf_yield"] = fcff / market_cap * 100
    return result


def derive_quality(entries: list[FinancialMetricEntry]) -> dict[str, float | None]:
    """盈利质量：现金流/净利润、现金流/营收、应计比率。"""
    result: dict[str, float | None] = {metric: None for metric in QUALITY_METRICS}
    ocf, _ = ttm_value(entries, "operating_cash_flow")
    net_income, _ = ttm_value(entries, "net_income")
    revenue, _ = ttm_value(entries, "revenue")
    assets, _ = _metric_latest(entries, "total_assets")

    if ocf is not None and net_income is not None and net_income > 0:
        result["cfo_to_ni"] = ocf / net_income
    if ocf is not None and revenue is not None and revenue > 0:
        result["cfo_to_revenue"] = ocf / revenue * 100
    if ocf is not None and net_income is not None and assets is not None and assets > 0:
        result["accrual_ratio"] = (net_income - ocf) / assets * 100
    return result


def derive_bank_metrics(entries: list[FinancialMetricEntry]) -> dict[str, float | None]:
    """银行专属派生指标：不良贷款率 = 不良贷款 / 贷款总额 × 100。"""
    npl, _ = _metric_latest(entries, "non_performing_loan")
    loans, _ = _metric_latest(entries, "gross_loans")
    ratio = npl / loans * 100 if npl is not None and loans and loans > 0 else None
    return {"npl_ratio": ratio}


def required_data_metrics(rule_metrics: set[str]) -> set[str]:
    """规则里出现派生指标时，精确追加计算它们所需的底层财务指标。"""
    metrics = set(rule_metrics)
    extra: set[str] = set()
    for metric in metrics & VALUATION_METRICS:
        extra |= _VALUATION_INPUT_MAP[metric]
    for metric in metrics & QUALITY_METRICS:
        extra |= _QUALITY_INPUT_MAP[metric]
    if metrics & BANK_METRICS:
        extra |= BANK_INPUTS
    return (metrics - VALUATION_METRICS - QUALITY_METRICS - BANK_METRICS) | extra
