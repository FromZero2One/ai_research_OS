"""比率层单测：纯函数 + 服务（PG 路径，子进程 mock）。"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from market.domain import FinancialMetricEntry
from market.models import FinancialMetric, ValuationHistory  # noqa: F401
from market.ratio_service import (
    RATIO_LABELS,
    RatioService,
    compute_ratios,
    percentile_rank,
)
from market.repositories import ValuationRepository


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


@pytest.mark.asyncio
async def test_valuation_repository_upsert_and_get(test_session: AsyncSession):
    repo = ValuationRepository(test_session)
    rows = [
        {"trade_date": date(2024, 1, 2), "pe": 10.0, "pe_ttm": 11.0, "pb": 1.2, "total_mv": 100.0},
        {"trade_date": date(2024, 1, 3), "pe": 10.5, "pe_ttm": 11.5, "pb": 1.3, "total_mv": 105.0},
    ]
    assert await repo.upsert("600000", rows) == 2
    # 重复 upsert 幂等
    assert await repo.upsert("600000", rows) == 0
    got = await repo.get_for_ticker("600000")
    assert len(got) == 2
    assert got[0].trade_date == date(2024, 1, 2)  # 升序


@pytest.mark.asyncio
async def test_read_ratios_from_pg(test_session: AsyncSession):
    test_session.add_all(
        [
            FinancialMetric(ticker="600000", fiscal_year=2024, fiscal_period="Annual", metric_name="revenue", metric_value=1000.0),
            FinancialMetric(ticker="600000", fiscal_year=2024, fiscal_period="Annual", metric_name="gross_profit", metric_value=400.0),
            FinancialMetric(ticker="600000", fiscal_year=2023, fiscal_period="Annual", metric_name="revenue", metric_value=800.0),
        ]
    )
    await test_session.commit()
    out = await RatioService(test_session).read_ratios("600000")
    assert len(out) == 2
    assert out[0]["gross_margin"] == 40.0
    assert out[0]["fiscal_year"] == 2024  # 倒序


@pytest.mark.asyncio
async def test_valuation_percentile_from_pg(test_session: AsyncSession):
    test_session.add_all(
        [
            ValuationHistory(ticker="600000", trade_date=date(2024, 1, 2), pe=10.0, pe_ttm=11.0, pb=1.2),
            ValuationHistory(ticker="600000", trade_date=date(2024, 1, 3), pe=20.0, pe_ttm=21.0, pb=2.2),
        ]
    )
    await test_session.commit()
    out = await RatioService(test_session).valuation_percentile("600000")
    assert out["available"] is True
    assert out["pe"]["current"] == 20.0
    assert out["pe"]["percentile"] == 100.0
    assert out["pe"]["samples"] == 2


@pytest.mark.asyncio
async def test_valuation_percentile_non_a_stock(test_session: AsyncSession):
    out = await RatioService(test_session).valuation_percentile("AAPL")
    assert out == {"ticker": "AAPL", "available": False, "reason": "non_a_stock"}


@pytest.mark.asyncio
async def test_valuation_percentile_fetch_on_miss(monkeypatch: pytest.MonkeyPatch, test_session: AsyncSession):
    """PG 不足 2 行时走 akshare 采集（mock 子进程），入库后算分位。"""
    fake_stdout = (
        '__R__:[{"trade_date": "2024-01-02", "pe": 10.0, "pe_ttm": 11.0, "pb": 1.2, "total_mv": 100.0}, '
        '{"trade_date": "2024-01-03", "pe": 15.0, "pe_ttm": 16.0, "pb": 1.5, "total_mv": 110.0}]'
    )

    def _fake_run(code, env=None):
        return fake_stdout

    monkeypatch.setattr("market.akshare_executor.run_akshare", _fake_run)
    out = await RatioService(test_session).valuation_percentile("600000")
    assert out["available"] is True
    assert out["pe"]["current"] == 15.0
    assert out["pe"]["percentile"] == 100.0
    rows = await ValuationRepository(test_session).get_for_ticker("600000")
    assert len(rows) == 2  # 已入库


@pytest.mark.asyncio
async def test_valuation_percentile_fetch_failure(monkeypatch: pytest.MonkeyPatch, test_session: AsyncSession):
    """akshare 失败 → available False，不抛错。"""
    monkeypatch.setattr("market.akshare_executor.run_akshare", lambda code, env=None: None)
    out = await RatioService(test_session).valuation_percentile("600000")
    assert out["available"] is False
