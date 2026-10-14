"""structured_facts 交叉验证 — 质检器（不进报告数字链路）。

分工原则（2026-10-14）：Market 接口是数字唯一事实源；财报 PDF 抽出的
structured_facts 只用于与接口值交叉比对。偏差 ≥10% 视为疑似口径差异
（合并 vs 归母、追溯调整、单位换算），生成观察事件提示分析师复核。

纯函数 + 简单单位换算，可单测。
"""

from __future__ import annotations

# 相对偏差阈值：超过视为疑似口径差异
DISCREPANCY_THRESHOLD = 0.10

# 货币单位 → 元 的换算系数（% / 倍 等比率单位必须完全一致才可比）
_CURRENCY_UNIT_TO_YUAN: dict[str, float] = {
    "元": 1.0,
    "万元": 1e4,
    "百万元": 1e6,
    "亿元": 1e8,
    "美元": 1.0,
}

_PERIOD_YEAR_MIN_LEN = 4


def _extract_year(period: str | None) -> int | None:
    """从自由文本报告期（如 "2025年报" / "FY2025"）提取 4 位年份。"""
    if not period:
        return None
    digits = ""
    for ch in period:
        if ch.isdigit():
            digits += ch
            if len(digits) == _PERIOD_YEAR_MIN_LEN:
                return int(digits)
        else:
            digits = ""
    return None


def _fact_value_in_metric_unit(
    value: float, fact_unit: str | None, metric_unit: str | None
) -> float | None:
    """把事实值换算到市场指标单位；无法可靠换算时返回 None（跳过比对）。

    双方都是货币单位 → 统一换算成"元"再比；
    双方都是比率/倍数类 → 要求单位完全一致；
    任一方单位未知 → 跳过。
    """
    if not fact_unit or not metric_unit:
        return None
    fu, mu = fact_unit.strip(), metric_unit.strip()
    if fu in _CURRENCY_UNIT_TO_YUAN and mu in _CURRENCY_UNIT_TO_YUAN:
        return value * _CURRENCY_UNIT_TO_YUAN[fu] / _CURRENCY_UNIT_TO_YUAN[mu]
    if fu == mu:
        return value
    return None


def compare_facts_with_market(
    facts: list[dict],
    market_metrics,
) -> list[str]:
    """比对我们抽取的结构化事实与 Market 接口指标，返回差异描述列表。

    ``market_metrics`` 为 FinancialMetric 对象序列（需含 metric_name /
    metric_value / metric_unit / fiscal_year / fiscal_period）。
    """
    # 索引：(归一化指标名, 年份) → 市场指标列表
    from market.models import normalize_metric_name

    market_index: dict[tuple[str, int], list] = {}
    for m in market_metrics:
        if m.metric_value is None:
            continue
        market_index.setdefault((str(m.metric_name), m.fiscal_year), []).append(m)

    discrepancies: list[str] = []
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        name, value, unit, period = (
            fact.get("metric_name"),
            fact.get("value"),
            fact.get("unit"),
            fact.get("period"),
        )
        if name is None or value is None or not isinstance(value, (int, float)):
            continue
        year = _extract_year(str(period) if period else None)
        if year is None:
            continue

        candidates = market_index.get((normalize_metric_name(str(name)), year), [])
        if not candidates:
            continue

        for m in candidates:
            fact_in_m = _fact_value_in_metric_unit(float(value), str(unit or ""), m.metric_unit)
            if fact_in_m is None:
                continue
            base = abs(float(m.metric_value))
            if base == 0:
                continue
            diff_pct = abs(fact_in_m - float(m.metric_value)) / base
            if diff_pct >= DISCREPANCY_THRESHOLD:
                discrepancies.append(
                    f"{name}（{period}）：原文 {value}{unit or ''} vs 接口 "
                    f"{m.metric_value}{m.metric_unit or ''}（{m.fiscal_year} "
                    f"{m.fiscal_period}），偏差 {diff_pct * 100:.1f}%，"
                    f"疑似口径差异（合并 vs 归母/追溯调整），建议复核"
                )
                break  # 同指标同期多条市场记录只报一条

    return discrepancies
