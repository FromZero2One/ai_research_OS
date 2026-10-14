"""fact_validator 纯函数单测（不依赖数据库）。"""

from __future__ import annotations

from dataclasses import dataclass

from research.fact_validator import (
    _extract_year,
    _fact_value_in_metric_unit,
    compare_facts_with_market,
)


@dataclass
class Metric:
    metric_name: str
    metric_value: float
    metric_unit: str | None
    fiscal_year: int
    fiscal_period: str = "Annual"


def _metric(name: str, value: float, unit: str, year: int = 2025, period: str = "Annual"):
    return Metric(
        metric_name=name, metric_value=value, metric_unit=unit, fiscal_year=year, fiscal_period=period
    )


class TestExtractYear:
    def test_common_periods(self):
        assert _extract_year("2025年报") == 2025
        assert _extract_year("FY2024") == 2024
        assert _extract_year("2025年第三季度") == 2025

    def test_invalid(self):
        assert _extract_year("最新一期") is None
        assert _extract_year(None) is None
        assert _extract_year("") is None


class TestUnitConversion:
    def test_currency_conversion(self):
        # 2579.36 亿元 = 25793600 万元
        assert _fact_value_in_metric_unit(2579.36, "亿元", "万元") == 25793600
        assert _fact_value_in_metric_unit(100, "百万元", "元") == 1e8

    def test_same_unit(self):
        assert _fact_value_in_metric_unit(15.2, "%", "%") == 15.2

    def test_incompatible_units_skip(self):
        assert _fact_value_in_metric_unit(15.2, "%", "元") is None
        assert _fact_value_in_metric_unit(15.2, None, "元") is None
        assert _fact_value_in_metric_unit(15.2, "%", None) is None


class TestCompareFacts:
    def test_consistent_no_discrepancy(self):
        facts = [{"metric_name": "营业收入", "value": 2579.36, "unit": "亿元", "period": "2025年报"}]
        metrics = [_metric("revenue", 25793600, "万元", 2025)]
        assert compare_facts_with_market(facts, metrics) == []

    def test_discrepancy_reported(self):
        facts = [{"metric_name": "营业收入", "value": 2000.0, "unit": "亿元", "period": "2025年报"}]
        metrics = [_metric("revenue", 25793600, "万元", 2025)]  # 2579.36 亿
        out = compare_facts_with_market(facts, metrics)
        assert len(out) == 1
        assert "疑似口径差异" in out[0]

    def test_year_mismatch_skipped(self):
        facts = [{"metric_name": "营业收入", "value": 1.0, "unit": "亿元", "period": "2025年报"}]
        metrics = [_metric("revenue", 25793600, "万元", 2024)]
        assert compare_facts_with_market(facts, metrics) == []

    def test_ratio_units_must_match(self):
        # 15.2% vs 12.8%（ROE，单位同为 %，偏差 >10%）
        facts = [{"metric_name": "净资产收益率", "value": 15.2, "unit": "%", "period": "2025年报"}]
        metrics = [_metric("roe", 12.8, "%", 2025)]
        assert len(compare_facts_with_market(facts, metrics)) == 1
        # 单位不一致（% vs 元）→ 无法换算，跳过
        metrics_bad = [_metric("roe", 12.8, "元", 2025)]
        assert compare_facts_with_market(facts, metrics_bad) == []

    def test_small_deviation_ignored(self):
        facts = [{"metric_name": "净利润", "value": 100.0, "unit": "亿元", "period": "2025年报"}]
        metrics = [_metric("net_income", 105e8, "元", 2025)]  # 偏差 5% < 10%
        assert compare_facts_with_market(facts, metrics) == []

    def test_unnormalized_fact_name(self):
        # 事实侧未归一化的名称也能通过 normalize_metric_name 匹配
        facts = [{"metric_name": "营收", "value": 2000.0, "unit": "亿元", "period": "2025年报"}]
        metrics = [_metric("revenue", 25793600, "万元", 2025)]
        assert len(compare_facts_with_market(facts, metrics)) == 1
