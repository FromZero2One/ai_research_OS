"""比率层单测：纯函数 + 服务（PG 路径，子进程 mock）。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from market.domain import FinancialMetricEntry
from market.ratio_service import (
    RATIO_LABELS,
    compute_ratios,
    percentile_rank,
)


def _entry(year: int, period: str, name: str, value: float | None) -> FinancialMetricEntry:
    return FinancialMetricEntry(
        fiscal_year=year, fiscal_period=period, metric_name=name, metric_value=value
    )


def test_compute_ratios_derived():
    metrics = [
        _entry(2024, "Annual", "revenue", 1000.0),
        _entry(2024, "Annual", "gross_profit", 400.0),
        _entry(2024, "Annual", "net_income", 100.0),
        _entry(2024, "Annual", "roe", 12.5),
    ]
    out = compute_ratios(metrics)
    assert len(out) == 1
    r = out[0]
    assert r["fiscal_year"] == 2024 and r["fiscal_period"] == "Annual"
    assert r["gross_margin"] == 40.0
    assert r["net_margin"] == 10.0
    assert r["roe"] == 12.5
    assert r["eps"] is None  # 缺原料 → None


def test_compute_ratios_zero_division_and_missing():
    metrics = [_entry(2024, "Annual", "gross_profit", 400.0)]  # 无 revenue
    out = compute_ratios(metrics)
    assert out[0]["gross_margin"] is None
    out2 = compute_ratios([_entry(2024, "Annual", "revenue", 0.0), _entry(2024, "Annual", "gross_profit", 1.0)])
    assert out2[0]["gross_margin"] is None
    assert compute_ratios([]) == []


def test_compute_ratios_annual_drops_same_year_quarters():
    metrics = [
        _entry(2024, "Annual", "revenue", 1000.0),
        _entry(2024, "Q4", "revenue", 900.0),   # 同年 Q4 被 Annual 挤掉
        _entry(2024, "Q1", "revenue", 200.0),
        _entry(2024, "Q1", "gross_profit", 80.0),
    ]
    out = compute_ratios(metrics)
    assert [r["fiscal_period"] for r in out] == ["Annual", "Q1"]
    assert out[0]["gross_margin"] is None
    assert out[1]["gross_margin"] == 40.0


def test_compute_ratios_multi_period_order():
    metrics = [
        _entry(2023, "Annual", "revenue", 800.0),
        _entry(2023, "Annual", "net_income", 80.0),
        _entry(2024, "Annual", "revenue", 1000.0),
        _entry(2024, "Annual", "net_income", 100.0),
    ]
    out = compute_ratios(metrics)
    assert [r["fiscal_year"] for r in out] == [2024, 2023]


def test_percentile_rank():
    assert percentile_rank([], 10) is None
    assert percentile_rank([5.0], 5.0) == 50.0
    assert percentile_rank([1, 2, 3, 4, 5], 3) == 60.0
    assert percentile_rank([1, 2, 3], 100) == 100.0
    assert percentile_rank([1, 2, 3], None) is None
    assert percentile_rank([1.0, 2.0], 0.5) == 0.0


def test_ratio_labels_complete():
    assert set(RATIO_LABELS) == {
        "gross_margin", "net_margin", "roe", "debt_to_equity", "asset_turnover",
        "inventory_turnover", "receivables_turnover", "current_ratio",
        "quick_ratio", "eps", "market_cap",
    }
