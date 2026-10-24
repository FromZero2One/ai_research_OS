"""推荐后表现单测 — 期限收益纯函数 + 服务层 T+1 计算。"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from market.models import StockPrice
from screener.models import ScreenerJudgement, ScreenerRun
from screener.performance import compute_stock_performance, summarize
from screener.performance_service import build_run_performance


class TestComputeStockPerformance:
    def test_horizon_returns(self):
        entry = date(2026, 1, 6)
        rows = [
            (date(2026, 1, 6), 100.0),
            (date(2026, 2, 6), 110.0),
            (date(2026, 4, 6), 90.0),
            (date(2026, 7, 6), 120.0),
            (date(2027, 1, 6), 130.0),
        ]
        out = compute_stock_performance(entry, 100.0, rows)
        assert out["current_return"] == pytest.approx(0.30)
        assert out["horizons"]["1m"] == pytest.approx(0.10)
        assert out["horizons"]["3m"] == pytest.approx(-0.10)
        assert out["horizons"]["6m"] == pytest.approx(0.20)
        assert out["horizons"]["12m"] == pytest.approx(0.30)

    def test_missing_entry_and_horizon(self):
        out = compute_stock_performance(date(2026, 1, 6), None, [])
        assert out["entry_price"] is None
        assert out["current_return"] is None
        assert all(v is None for v in out["horizons"].values())

        out = compute_stock_performance(
            date(2026, 1, 6), 100.0, [(date(2026, 1, 6), 101.0)]
        )
        assert out["horizons"]["1m"] is None  # 目标日之后没有价格

    def test_summary(self):
        rows = [
            {"current_return": 0.1, "horizons": {"1m": 0.1, "3m": None}},
            {"current_return": -0.2, "horizons": {"1m": -0.1, "3m": None}},
        ]
        summary = summarize(rows)
        assert summary["1m"]["count"] == 2
        assert summary["1m"]["avg_return"] == pytest.approx(0.0)
        assert summary["1m"]["hit_rate"] == pytest.approx(0.5)
        assert summary["3m"] == {"count": 0, "avg_return": None, "hit_rate": None}


async def test_build_run_performance_t_plus_one(test_session: AsyncSession):
    run = ScreenerRun(
        criteria_hash="h", criteria_text="标准", mode="presets",
        preset_ids=["p"], combine_mode="union", status="completed",
        candidate_count=2, result_count=2,
        created_at=datetime(2026, 1, 5, 9, 0, tzinfo=UTC),
    )
    test_session.add(run)
    await test_session.flush()

    for ticker, name, industry in (
        ("AAA", "甲", "银行"), ("BBB", "乙", "电子"),
    ):
        test_session.add(
            ScreenerJudgement(
                run_id=run.id, ticker=ticker, name=name, recommend=True,
                reasons=[], criteria_hits=[], confidence=0.9,
                snapshot={"industry": industry}, status="ok",
            )
        )
    for ticker, prices in (
        ("AAA", [(date(2026, 1, 6), 100.0), (date(2026, 2, 6), 110.0)]),
        ("BBB", [(date(2026, 1, 6), 50.0), (date(2026, 2, 6), 45.0)]),
    ):
        for day, close in prices:
            test_session.add(StockPrice(ticker=ticker, date=day, close=close))
    await test_session.flush()

    result = await build_run_performance(test_session, run.id)
    assert result["recommended_count"] == 2
    assert result["with_entry_price"] == 2
    assert result["summary"]["1m"]["avg_return"] == pytest.approx(0.0)
    assert result["summary"]["1m"]["hit_rate"] == pytest.approx(0.5)
    by_ticker = {s["ticker"]: s for s in result["stocks"]}
    assert by_ticker["AAA"]["entry_price"] == 100.0
    assert by_ticker["AAA"]["horizons"]["1m"] == pytest.approx(0.10)
    assert by_ticker["BBB"]["horizons"]["1m"] == pytest.approx(-0.10)
