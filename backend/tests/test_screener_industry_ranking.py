"""行业相对排名单测 — 行业分位 + 行业集中度上限。"""

from __future__ import annotations

from market.domain import FinancialMetricEntry
from screener.industry_ranking import compute_industry_percentiles
from screener.screening import cap_by_industry


def _e(metric: str, value: float) -> FinancialMetricEntry:
    return FinancialMetricEntry(
        fiscal_year=2026, fiscal_period="Q2", metric_name=metric, metric_value=value
    )


def _cand(ticker: str, market_cap: float = 1e10) -> dict:
    return {
        "ticker": ticker, "name": ticker, "industry": "银行", "sector": "financial",
        "market_cap": market_cap,
    }


class TestIndustryPercentiles:
    def test_higher_roe_and_lower_pe_pb_score_better(self):
        pool = [_cand(t) for t in ("A", "B", "C", "D")]
        financials = {}
        for i, ticker in enumerate(("A", "B", "C", "D")):
            financials[ticker] = [
                _e("roe", 10.0 * (i + 1)),
                _e("net_income", 1e8 * (i + 1)),
                _e("total_assets", 1e12),
                _e("total_liabilities", 9e11 - i * 1e11),
            ]

        result = compute_industry_percentiles(pool, financials)
        assert result["D"]["industry_percentiles"]["roe"] == 1.0
        assert result["A"]["industry_percentiles"]["roe"] == 0.0
        # PE 越低越好（已反转）
        assert result["D"]["industry_percentiles"]["pe"] > result["A"]["industry_percentiles"]["pe"]
        # PB 越低越好（已反转），D 净资产最大 → 分位最高
        assert result["D"]["industry_percentiles"]["pb"] == 1.0
        assert result["D"]["industry_score"] > result["A"]["industry_score"]

    def test_small_industry_is_neutral(self):
        pool = [_cand("A"), _cand("B")]
        financials = {
            "A": [_e("roe", 10.0)],
            "B": [_e("roe", 20.0)],
        }
        result = compute_industry_percentiles(pool, financials)
        assert result["A"]["industry_percentiles"]["roe"] == 0.5
        assert result["B"]["industry_percentiles"]["roe"] == 0.5


class TestIndustryCap:
    def test_caps_per_industry(self):
        cands = [{"ticker": str(i), "industry": "银行"} for i in range(10)]
        out = cap_by_industry(cands, max_per_industry=3, limit=50)
        assert len(out) == 3

    def test_fills_from_other_industries(self):
        cands = (
            [{"ticker": f"B{i}", "industry": "银行"} for i in range(4)]
            + [{"ticker": f"E{i}", "industry": "电子"} for i in range(3)]
        )
        out = cap_by_industry(cands, max_per_industry=2, limit=50)
        assert [c["industry"] for c in out] == ["银行", "银行", "电子", "电子"]

    def test_limit_after_cap(self):
        cands = [{"ticker": str(i), "industry": f"行业{i}"} for i in range(10)]
        out = cap_by_industry(cands, max_per_industry=1, limit=3)
        assert len(out) == 3
