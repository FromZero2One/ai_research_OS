"""stock_prices 唯一约束测试（BacktestRun 模型已删，表保留）。"""

from __future__ import annotations


def test_stock_prices_unique_constraint():
    """market.stock_prices 必须有 (ticker, date) 唯一约束（幂等灌库前提）。"""
    from market.models import StockPrice

    uniques = [
        c for c in StockPrice.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    cols = {frozenset(col.name for col in u.columns) for u in uniques}
    assert frozenset({"ticker", "date"}) in cols, f"缺 (ticker,date) 唯一约束: {cols}"
