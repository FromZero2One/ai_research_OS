"""BacktestRun 模型 + stock_prices 唯一约束测试。"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import CriteriaPreset, ScreenerBacktestRun


async def test_backtest_run_crud(test_session: AsyncSession):
    """建行 → flush → 查询：列齐全、默认值正确。"""
    preset_id = uuid.uuid4()
    run = ScreenerBacktestRun(preset_id=preset_id, years=5, status="pending")
    test_session.add(run)
    await test_session.flush()

    row = (
        await test_session.execute(
            select(ScreenerBacktestRun).where(ScreenerBacktestRun.id == run.id)
        )
    ).scalar_one()
    assert row.preset_id == preset_id
    assert row.years == 5
    assert row.status == "pending"
    assert row.error is None
    assert row.result is None
    assert row.report_path is None


def test_stock_prices_unique_constraint():
    """market.stock_prices 必须有 (ticker, date) 唯一约束（幂等灌库前提）。"""
    from market.models import StockPrice

    uniques = [
        c for c in StockPrice.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    cols = {frozenset(col.name for col in u.columns) for u in uniques}
    assert frozenset({"ticker", "date"}) in cols, f"缺 (ticker,date) 唯一约束: {cols}"
