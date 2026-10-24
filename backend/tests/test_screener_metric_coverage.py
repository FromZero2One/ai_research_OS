"""指标可用性预检 — 指标在全市场完全无数据时显式失败，而不是静默 0 候选。"""

from __future__ import annotations

from screener.service import metrics_without_any_data


class _Entry:
    def __init__(self, metric_name: str) -> None:
        self.metric_name = metric_name


class TestMetricsWithoutAnyData:
    def test_snapshot_metrics_never_need_financial_rows(self):
        assert metrics_without_any_data({"price", "turnover", "market_cap"}, {}) == []

    def test_missing_financial_metric_reported(self):
        financials = {"600519": [_Entry("roe")]}
        assert metrics_without_any_data({"roe", "rd_expense"}, financials) == ["rd_expense"]

    def test_one_ticker_with_data_is_enough(self):
        """部分覆盖是正常的（指标有缺票），只有全市场零覆盖才算不可用。"""
        assert metrics_without_any_data({"roe"}, {"600519": [_Entry("roe")]}) == []
