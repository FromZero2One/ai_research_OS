"""_reload_financials 过滤行为单测 — 只拉所需指标 + 指定报告期，防止全表加载。"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from market.models import FinancialMetric
from screener.service import _reload_financials


def _metric_row(ticker: str, year: int, period: str, name: str, value: float) -> FinancialMetric:
    return FinancialMetric(
        id=uuid.uuid4(),
        ticker=ticker,
        fiscal_year=year,
        fiscal_period=period,
        metric_name=name,
        metric_value=value,
    )


@pytest.fixture
async def seeded_financials(test_session: AsyncSession):
    """造 4 行数据：目标期 roe、无关指标 eps、旧期 roe、无关票。"""
    test_session.add_all([
        _metric_row("600519", 2026, "Q2", "roe", 30.0),      # 目标：最新期 + 所需指标
        _metric_row("600519", 2026, "Q2", "eps", 5.0),        # 同期但不在所需指标里
        _metric_row("600519", 2025, "Q4", "roe", 28.0),       # 所需指标但旧期
        _metric_row("300750", 2026, "Q2", "roe", 20.0),       # 另一只票（应保留）
    ])
    await test_session.flush()


async def test_filters_by_metrics_and_period(test_session: AsyncSession, seeded_financials):
    """只加载所需指标 + 指定报告期：eps（指标不符）与 2025Q4（期不符）不入内存。"""
    fin = await _reload_financials(
        test_session,
        metrics={"roe"},
        year=2026,
        period="Q2",
    )
    assert set(fin.keys()) == {"600519", "300750"}
    names = [e.metric_name for e in fin["600519"]]
    assert names == ["roe"]  # eps 被过滤
    periods = {(e.fiscal_year, e.fiscal_period) for e in fin["600519"]}
    assert periods == {(2026, "Q2")}  # 2025Q4 旧期被过滤


async def test_no_filters_loads_all(test_session: AsyncSession, seeded_financials):
    """不传过滤条件时保持旧行为（全量加载），向后兼容。"""
    fin = await _reload_financials(test_session)
    assert set(fin.keys()) == {"600519", "300750"}
    assert len(fin["600519"]) == 3
