"""period_compare 纯函数单测（不依赖数据库）。"""

from __future__ import annotations

from research.period_compare import (
    build_peer_comparison_lines,
    build_period_comparison_block,
    compare_facts_periods,
    parse_period,
)


def _ev(facts: list[dict] | None):
    class E:
        id = "e1"
        structured_facts = {"facts": facts or [], "not_mentioned": not facts}

    return E()


class TestParsePeriod:
    def test_annual(self):
        assert parse_period("2024年报") == (2024, "annual", 0)
        assert parse_period("2024年度") == (2024, "annual", 0)

    def test_quarter(self):
        assert parse_period("2025Q1") == (2025, "q1", 1)
        assert parse_period("2024q4") == (2024, "q4", 4)
        assert parse_period("2025年第三季度") == (2025, "q3", 3)
        assert parse_period("2025年一季度") == (2025, "q1", 1)

    def test_semi(self):
        assert parse_period("2024中报") == (2024, "semi", 0)
        assert parse_period("2024半年报") == (2024, "semi", 0)

    def test_invalid(self):
        assert parse_period("最新一期") is None
        assert parse_period(None) is None
        assert parse_period("") is None


class TestCompareFactsPeriods:
    def test_yoy_annual(self):
        facts = [
            {"metric_name": "revenue", "value": 110.0, "unit": "亿元", "period": "2024年报"},
            {"metric_name": "revenue", "value": 100.0, "unit": "亿元", "period": "2023年报"},
        ]
        lines = compare_facts_periods(facts)
        assert len(lines) == 1
        assert "YoY" in lines[0] and "+10.0%" in lines[0]

    def test_quarter_yoy_only(self):
        # 2024Q1 → 2025Q1：跨年同季是 YoY，但非严格相邻（缺 Q2-Q4），无 QoQ
        facts = [
            {"metric_name": "revenue", "value": 30.0, "unit": "亿元", "period": "2025Q1"},
            {"metric_name": "revenue", "value": 20.0, "unit": "亿元", "period": "2024Q1"},
        ]
        lines = compare_facts_periods(facts)
        assert len(lines) == 1 and "YoY" in lines[0] and "+50.0%" in lines[0]

    def test_qoq_same_year(self):
        facts = [
            {"metric_name": "revenue", "value": 32.0, "unit": "亿元", "period": "2024Q4"},
            {"metric_name": "revenue", "value": 25.0, "unit": "亿元", "period": "2024Q3"},
        ]
        lines = compare_facts_periods(facts)
        assert len(lines) == 1 and "QoQ" in lines[0] and "+28.0%" in lines[0]

    def test_non_adjacent_quarters_skipped(self):
        # 2024Q3 → 2025Q1 缺 2024Q4，既非相邻也非同比，不输出
        facts = [
            {"metric_name": "revenue", "value": 30.0, "unit": "亿元", "period": "2025Q1"},
            {"metric_name": "revenue", "value": 24.0, "unit": "亿元", "period": "2024Q3"},
        ]
        assert compare_facts_periods(facts) == []

    def test_unit_mismatch_skipped(self):
        facts = [
            {"metric_name": "revenue", "value": 110.0, "unit": "亿元", "period": "2024年报"},
            {"metric_name": "revenue", "value": 100000.0, "unit": "万元", "period": "2023年报"},
        ]
        assert compare_facts_periods(facts) == []

    def test_zero_base(self):
        facts = [
            {"metric_name": "net_income", "value": 5.0, "unit": "亿元", "period": "2024年报"},
            {"metric_name": "net_income", "value": 0.0, "unit": "亿元", "period": "2023年报"},
        ]
        lines = compare_facts_periods(facts)
        assert lines and "无法计算" in lines[0]


class TestBuildBlock:
    def test_block_with_data(self):
        facts = [
            {"metric_name": "revenue", "value": 110.0, "unit": "亿元", "period": "2024年报"},
            {"metric_name": "revenue", "value": 100.0, "unit": "亿元", "period": "2023年报"},
        ]
        block = build_period_comparison_block([_ev(facts)])
        assert block is not None and "Multi-period" in block and "计算得出" in block

    def test_block_empty(self):
        assert build_period_comparison_block([_ev(None)]) is None
        assert build_period_comparison_block([]) is None


class TestPeerLines:
    def test_median_comparison(self):
        subject = {"revenue": 120.0}
        peers = {"revenue": {"A": [80.0], "B": [100.0], "C": [140.0]}}
        lines = build_peer_comparison_lines("SUB", subject, peers)
        assert len(lines) == 1
        assert "100" in lines[0]  # median of 80/100/140
        assert "20.0%" in lines[0]  # (120-100)/100
        assert "高于" in lines[0]

    def test_insufficient_peers(self):
        peers = {"revenue": {"A": [80.0]}}
        assert build_peer_comparison_lines("SUB", {"revenue": 120.0}, peers) == []
