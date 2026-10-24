"""回测核心纯函数单测 — 调仓日、无未来函数、停牌处理、净值指标。"""

from __future__ import annotations

import datetime as dt

import pytest

from screener.backtest import (
    build_disclosure_map,
    compute_holding_returns,
    compute_nav_and_stats,
    generate_rebalance_dates,
    pick_financial_period,
)


class TestDisclosureMap:
    def test_known_periods(self):
        m = build_disclosure_map()
        assert m[(2021, "Q1")] == dt.date(2021, 4, 30)
        assert m[(2021, "Q2")] == dt.date(2021, 8, 31)
        assert m[(2021, "Q3")] == dt.date(2021, 10, 31)
        assert m[(2021, "Q4")] == dt.date(2022, 4, 30)  # 年报次年 4-30


class TestPickFinancialPeriod:
    def test_no_lookahead_reuses_only_disclosed_period(self):
        """Review Focus 1：调仓日 2022-05-10 只能见到 2021Q4 及更早。"""
        assert pick_financial_period(dt.date(2022, 5, 10)) == (2021, "Q4")

    def test_after_august_uses_q2(self):
        """8-31 之后最近披露的是当年中报。"""
        assert pick_financial_period(dt.date(2022, 9, 15)) == (2022, "Q2")

    def test_after_october_uses_q3(self):
        assert pick_financial_period(dt.date(2022, 11, 1)) == (2022, "Q3")

    def test_before_first_disclosure_raises(self):
        """起点太早（无可披露报告期）→ raise。"""
        with pytest.raises(ValueError):
            pick_financial_period(dt.date(1995, 1, 1))


class TestGenerateRebalanceDates:
    def test_basic_series(self):
        """各披露截止日后的首个交易日，升序。"""
        # 交易日历：2021-05-06（5-1 假期后）、2021-09-01、2021-11-01、2022-05-05
        price_dates = [
            dt.date(2021, 5, 6), dt.date(2021, 9, 1), dt.date(2021, 11, 1),
            dt.date(2022, 5, 5),
        ]
        out = generate_rebalance_dates(price_dates, dt.date(2021, 1, 1), dt.date(2022, 12, 31))
        assert out == [dt.date(2021, 5, 6), dt.date(2021, 9, 1), dt.date(2021, 11, 1), dt.date(2022, 5, 5)]

    def test_dedupes_same_day(self):
        """年报截止日与 Q1 截止日重合（4-30）→ 只产生一个调仓日。"""
        price_dates = [dt.date(2022, 5, 5)]
        out = generate_rebalance_dates(price_dates, dt.date(2021, 1, 1), dt.date(2022, 12, 31))
        assert out == [dt.date(2022, 5, 5)]

    def test_empty_calendar_raises(self):
        """Review Focus 3：空日历 raise，不产出退化回测。"""
        with pytest.raises(ValueError, match="无价格日历"):
            generate_rebalance_dates([], dt.date(2021, 1, 1), dt.date(2022, 12, 31))

    def test_cutoff_dates_outside_range_skipped(self):
        """截止日不在回测区间内 → 不生成对应调仓日。"""
        price_dates = [dt.date(2021, 5, 6), dt.date(2021, 9, 1)]
        out = generate_rebalance_dates(price_dates, dt.date(2021, 6, 1), dt.date(2021, 12, 31))
        assert out == [dt.date(2021, 9, 1)]  # 2021-04-30 截止日 < start(6-1)


class TestComputeHoldingReturns:
    def test_simple_return(self):
        portfolio = [{"ticker": "600519", "name": "茅台"}]
        out = compute_holding_returns(
            portfolio, buy_prices={"600519": 100.0}, sell_prices={"600519": 110.0}
        )
        assert out[0]["return"] == pytest.approx(0.10)
        assert out[0]["suspended"] is False

    def test_costs_applied_to_round_trip(self):
        portfolio = [{"ticker": "600519", "name": "茅台"}]
        out = compute_holding_returns(
            portfolio,
            buy_prices={"600519": 100.0},
            sell_prices={"600519": 110.0},
            cost_buy=0.0013,
            cost_sell=0.0018,
        )
        expected = (110.0 * (1 - 0.0018)) / (100.0 * (1 + 0.0013)) - 1.0
        assert out[0]["return"] == pytest.approx(expected)

    def test_suspended_stock_zero_return(self):
        """Review Focus 4：卖出价缺失（停牌）→ 收益 0 + suspended 标注。"""
        portfolio = [{"ticker": "600519", "name": "茅台"}]
        out = compute_holding_returns(portfolio, buy_prices={"600519": 100.0}, sell_prices={})
        assert out[0]["return"] == 0.0
        assert out[0]["suspended"] is True


class TestNavAndStats:
    def _period(self, year: int, ret: float, bench: float, holdings: list | None = None) -> dict:
        return {"year": year, "rebalance_date": f"{year}-05-06", "return": ret, "bench": bench,
                "holdings": holdings or []}

    def test_nav_stats_exact(self):
        periods = [
            self._period(2021, 0.10, 0.05),
            self._period(2022, -0.10, -0.05),
            self._period(2023, 0.21, 0.00),
        ]
        stats = compute_nav_and_stats(periods)
        # 累计 = 1.1 × 0.9 × 1.21 - 1 = 0.1979
        assert stats["total_return"] == pytest.approx(0.1979, rel=1e-6)
        # 基准累计 = 1.05 × 0.95 × 1.0 - 1 = -0.0025
        assert stats["bench_total_return"] == pytest.approx(-0.0025, rel=1e-6)
        # 净值序列 [1, 1.1, 0.99, 1.1989]；最大回撤 = (1.1 → 0.99) = -0.1
        assert stats["max_drawdown"] == pytest.approx(-0.1, rel=1e-6)
        # 年度胜率 = 2021 超额 +5%、2022 超额 -5%、2023 超额 +21% → 2/3
        assert stats["win_rate"] == pytest.approx(2 / 3)
        assert len(stats["yearly"]) == 3
