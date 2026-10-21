"""确定性初筛单测 — 规则求值（纯函数）+ 快照采集（mock akshare）。"""

from __future__ import annotations

from datetime import date

import pytest

from market.domain import FinancialMetricEntry
from screener.screening import (
    evaluate_quant_rules,
    fetch_market_spot,
    rank_candidates,
    score_candidate,
)


def _entry(year: int, period: str, name: str, value: float | None) -> FinancialMetricEntry:
    return FinancialMetricEntry(fiscal_year=year, fiscal_period=period, metric_name=name, metric_value=value)


def _c(ticker: str, price: float = 10.0, market_cap: float = 100.0, turnover: float = 1.5) -> dict:
    return {"ticker": ticker, "name": ticker, "price": price, "turnover": turnover, "market_cap": market_cap}


RULE_ROE = {"metric": "roe", "op": ">", "value": 15.0, "missing_data_policy": "exclude"}
RULE_PRICE = {"metric": "price", "op": "<=", "value": 20.0, "missing_data_policy": "exclude"}

FIN = {"600519": [_entry(2024, "Annual", "roe", 30.0)]}


class TestEvaluateQuantRules:
    def test_metric_hit_and_miss(self):
        candidates = [_c("600519"), _c("300750")]
        passed, excluded = evaluate_quant_rules(candidates, [RULE_ROE], FIN)
        assert [c["ticker"] for c in passed] == ["600519"]
        # 净资产收益率不命中且策略 exclude → 进 excluded（缺数据）
        assert [c["ticker"] for c in excluded] == ["300750"]

    def test_missing_data_exclude_even_with_other_hits(self):
        """exclude 策略的规则缺数据 → 即使命中其他规则也必须排除。"""
        rule_missing = {"metric": "roe", "op": ">", "value": 15.0, "missing_data_policy": "exclude"}
        candidates = [_c("300750", price=8.0)]  # price 命中、roe 缺数据
        passed, excluded = evaluate_quant_rules(candidates, [RULE_PRICE, rule_missing], {})
        assert passed == []
        assert [c["ticker"] for c in excluded] == ["300750"]
        assert excluded[0]["missing"] == ["roe"]  # 报告需要列出缺失指标

    def test_excluded_carries_missing_list(self):
        rule_a = {"metric": "roe", "op": ">", "value": 15.0, "missing_data_policy": "exclude"}
        rule_b = {"metric": "eps", "op": ">", "value": 1.0, "missing_data_policy": "exclude"}
        passed, excluded = evaluate_quant_rules([_c("300750")], [rule_a, rule_b], {})
        assert excluded[0]["missing"] == ["roe", "eps"]

    def test_snapshot_field(self):
        passed, _ = evaluate_quant_rules([_c("600519", price=8.0), _c("300750", price=25.0)], [RULE_PRICE], {})
        assert [c["ticker"] for c in passed] == ["600519"]

    def test_missing_data_include(self):
        rule = {"metric": "roe", "op": ">", "value": 15.0, "missing_data_policy": "include"}
        passed, excluded = evaluate_quant_rules([_c("300750")], [rule], {})
        assert len(passed) == 1  # include：缺数据放行并计入命中
        assert excluded == []

    def test_latest_period_used(self):
        """同指标多期时取最新一期。"""
        fin = {"600519": [_entry(2023, "Annual", "roe", 5.0), _entry(2024, "Annual", "roe", 30.0)]}
        passed, _ = evaluate_quant_rules([_c("600519")], [RULE_ROE], fin)
        assert len(passed) == 1

    def test_no_rules_passes_all(self):
        passed, excluded = evaluate_quant_rules([_c("600519")], [], {})
        assert len(passed) == 1
        assert excluded == []


class TestScoreAndRank:
    def test_score_ratio(self):
        assert score_candidate(hit=2, applicable=4) == 0.5

    def test_score_zero_applicable(self):
        assert score_candidate(hit=0, applicable=0) == 0.0

    def test_rank_sorts_by_score_then_market_cap(self):
        a = {**_c("A"), "score": 0.5, "market_cap": 100.0}
        b = {**_c("B"), "score": 0.8, "market_cap": 10.0}
        c1 = {**_c("C"), "score": 0.5, "market_cap": 200.0}
        ranked = rank_candidates([a, b, c1], limit=50)
        assert [r["ticker"] for r in ranked] == ["B", "C", "A"]

    def test_rank_truncates(self):
        cands = [{**_c(str(i)), "score": 0.1, "market_cap": float(i)} for i in range(10)]
        assert len(rank_candidates(cands, limit=3)) == 3


class TestFetchMarketSpot:
    async def test_parse_ok(self, monkeypatch):
        import json

        sample = [{"ticker": "600519", "name": "贵州茅台", "price": 1500.5, "turnover": 0.32, "market_cap": 1.88e12}]
        monkeypatch.setattr(
            "screener.screening.run_akshare",
            lambda code, env_args=None, timeout=60: "__R__:" + json.dumps(sample, ensure_ascii=False),
        )
        spot = await fetch_market_spot()
        assert spot[0]["ticker"] == "600519"
        assert spot[0]["price"] == 1500.5
        assert spot[0]["market_cap"] == 1.88e12

    async def test_dirty_numeric_becomes_none(self, monkeypatch):
        """akshare 对停牌股返回 '-' / NaN → 数值字段清洗为 None（走缺数据路径）。"""
        import json

        sample = [{"ticker": "000001", "name": "平安银行", "price": "-", "turnover": None, "market_cap": "NaN"}]
        monkeypatch.setattr(
            "screener.screening.run_akshare",
            lambda code, env_args=None, timeout=60: "__R__:" + json.dumps(sample),
        )
        spot = await fetch_market_spot()
        assert spot[0]["price"] is None
        assert spot[0]["turnover"] is None
        assert spot[0]["market_cap"] is None

    async def test_akshare_none_raises(self, monkeypatch):
        monkeypatch.setattr("screener.screening.run_akshare", lambda code, env_args=None, timeout=60: None)
        with pytest.raises(Exception):
            await fetch_market_spot()
