"""估值派生指标单测 — PE/PB/PS 纯函数 + 底层数据依赖映射。"""

from __future__ import annotations

from market.domain import FinancialMetricEntry
from screener.valuation import (
    QUALITY_INPUTS,
    annualization_factor,
    derive_quality,
    derive_valuation,
    required_data_metrics,
    ttm_value,
)


def _e(metric: str, value: float, period: str = "Q2", year: int = 2026):
    return FinancialMetricEntry(
        metric_name=metric, metric_value=value, fiscal_year=year, fiscal_period=period
    )


class TestAnnualization:
    def test_factors(self):
        assert annualization_factor("Q1") == 4.0
        assert annualization_factor("Q2") == 2.0
        assert annualization_factor("Q3") == 4.0 / 3.0
        assert annualization_factor("Q4") == 1.0
        assert annualization_factor("Annual") == 1.0
        assert annualization_factor(None) == 1.0


class TestDeriveValuation:
    def test_pe_pb_ps(self):
        candidate = {"market_cap": 1e10}
        financials = [
            _e("net_income", 5e8),          # 年化 1e9 → PE 10
            _e("revenue", 2e9),             # 年化 4e9 → PS 2.5
            _e("total_assets", 8e9),
            _e("total_liabilities", 3e9),   # 净资产 5e9 → PB 2
        ]
        values = derive_valuation(candidate, financials)
        assert values["pe"] == 10.0
        assert values["pb"] == 2.0
        assert values["ps"] == 2.5

    def test_negative_earnings_pe_missing(self):
        values = derive_valuation({"market_cap": 1e10}, [_e("net_income", -1e8)])
        assert values["pe"] is None

    def test_non_positive_equity_pb_missing(self):
        values = derive_valuation(
            {"market_cap": 1e10},
            [_e("total_assets", 3e9), _e("total_liabilities", 4e9)],
        )
        assert values["pb"] is None

    def test_missing_market_cap(self):
        values = derive_valuation({}, [_e("net_income", 5e8)])
        assert values == {"pe": None, "pb": None, "ps": None}

    def test_uses_latest_period(self):
        financials = [
            _e("net_income", 1e8, "Q1"),
            _e("net_income", 6e8, "Q2"),
        ]
        # 无历史期 → 回退 Q2 年化（×2）：1e10 / (6e8*2)
        assert derive_valuation({"market_cap": 1e10}, financials)["pe"] == 1e10 / 1.2e9

    def test_ttm_from_annual_plus_ytd_minus_prior_ytd(self):
        financials = [
            _e("net_income", 1.2e9, "Q4", 2025),
            _e("net_income", 6e8, "Q2", 2026),
            _e("net_income", 4e8, "Q2", 2025),
            _e("revenue", 4e9, "Q4", 2025),
            _e("revenue", 2.2e9, "Q2", 2026),
            _e("revenue", 1.5e9, "Q2", 2025),
            _e("total_assets", 8e9),
            _e("total_liabilities", 3e9),
        ]
        values = derive_valuation({"market_cap": 1e10}, financials)
        assert values["pe"] == 1e10 / 1.4e9      # FY2025 + 2026H1 - 2025H1
        assert values["ps"] == 1e10 / 4.7e9
        assert values["pb"] == 2.0

    def test_ttm_marks_strict_vs_fallback(self):
        strict, is_ttm = ttm_value(
            [
                _e("net_income", 1.2e9, "Q4", 2025),
                _e("net_income", 6e8, "Q2", 2026),
                _e("net_income", 4e8, "Q2", 2025),
            ],
            "net_income",
        )
        assert strict == 1.4e9 and is_ttm is True
        fallback, is_ttm = ttm_value([_e("net_income", 6e8, "Q2", 2026)], "net_income")
        assert fallback == 1.2e9 and is_ttm is False


class TestDeriveQuality:
    def test_quality_ratios(self):
        financials = [
            _e("operating_cash_flow", 7e8, "Q2", 2026),
            _e("net_income", 5e8, "Q2", 2026),
            _e("revenue", 2e9, "Q2", 2026),
            _e("total_assets", 8e9, "Q2", 2026),
        ]
        q = derive_quality(financials)
        assert q["cfo_to_ni"] == 1.4
        assert q["cfo_to_revenue"] == 35.0
        assert q["accrual_ratio"] == -5.0

    def test_negative_profit_has_no_cfo_ratio(self):
        q = derive_quality([
            _e("operating_cash_flow", 1e8, "Q2", 2026),
            _e("net_income", -5e7, "Q2", 2026),
            _e("total_assets", 8e9, "Q2", 2026),
        ])
        assert q["cfo_to_ni"] is None
        assert q["accrual_ratio"] is not None


class TestRequiredDataMetrics:
    def test_pe_only_loads_net_income(self):
        assert required_data_metrics({"pe", "market_cap"}) == {"market_cap", "net_income"}

    def test_pb_loads_balance_sheet_items(self):
        assert required_data_metrics({"pb"}) == {"total_assets", "total_liabilities"}

    def test_ps_loads_revenue(self):
        assert required_data_metrics({"ps"}) == {"revenue"}

    def test_quality_loads_precise_inputs(self):
        assert required_data_metrics({"cfo_to_ni"}) == {
            "operating_cash_flow", "net_income"
        }
        assert required_data_metrics({"accrual_ratio"}) == {
            "operating_cash_flow", "net_income", "total_assets"
        }
        assert QUALITY_INPUTS == {
            "operating_cash_flow", "net_income", "revenue", "total_assets"
        }

    def test_non_valuation_unchanged(self):
        assert required_data_metrics({"roe", "market_cap"}) == {"roe", "market_cap"}
