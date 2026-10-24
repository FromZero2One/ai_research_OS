"""组合再平衡 — 纯函数 + API。"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from market.models import StockPrice
from screener.models import ScreenerPortfolio
from screener.rebalance import compute_rebalance


def _h(ticker: str, amount: float, price: float, weight: float) -> dict:
    return {
        "ticker": ticker, "name": ticker, "industry": "测试",
        "price": price, "amount": amount, "weight": weight,
    }


def test_drift_and_actions():
    holdings = [_h("AAA", 5000, 10, 0.5), _h("BBB", 5000, 10, 0.5)]
    out = compute_rebalance(holdings, {"AAA": 20.0, "BBB": 10.0})
    assert out["total_value"] == pytest.approx(15000)
    by = {h["ticker"]: h for h in out["holdings"]}
    assert by["AAA"]["current_weight"] == pytest.approx(2 / 3)
    assert by["AAA"]["action"] == "sell"
    assert by["AAA"]["shares_delta"] == -125
    assert by["BBB"]["action"] == "buy"
    assert by["BBB"]["shares_delta"] == 200  # 250 股按 100 股一手向下取整
    assert out["summary"] == {"buys": 1, "sells": 1, "holds": 0}


def test_small_drift_is_hold():
    holdings = [_h("AAA", 5000, 10, 0.5), _h("BBB", 5000, 10, 0.5)]
    out = compute_rebalance(holdings, {"AAA": 10.1, "BBB": 10.0}, tolerance=0.01)
    assert out["summary"]["buys"] == 0
    assert out["summary"]["sells"] == 0


def test_missing_price_falls_back_and_flags_stale():
    holdings = [_h("AAA", 5000, 10, 0.5), _h("BBB", 5000, 10, 0.5)]
    out = compute_rebalance(holdings, {"AAA": 20.0})
    by = {h["ticker"]: h for h in out["holdings"]}
    assert by["BBB"]["stale_price"] is True
    assert by["BBB"]["current_price"] == 10.0
    assert by["BBB"]["action"] == "hold"


def test_buy_below_one_lot_is_blocked():
    holdings = [_h("AAA", 500, 10, 0.5), _h("BBB", 500, 10, 0.5)]
    out = compute_rebalance(holdings, {"AAA": 20.0, "BBB": 10.0})
    by = {h["ticker"]: h for h in out["holdings"]}
    assert by["BBB"]["action"] == "hold"
    assert by["BBB"]["lot_blocked"] is True


async def test_rebalance_api(
    client, test_session: AsyncSession
):
    portfolio = ScreenerPortfolio(
        run_id=None,  # 直接在测试库构造；FK 在 PG 中要求存在，故另建 run
        name="测试组合",
        params={"capital": 10000},
        result={
            "holdings": [_h("AAA", 5000, 10, 0.5), _h("BBB", 5000, 10, 0.5)],
            "cash": 0.0,
        },
    )
    # run_id 非空：先建一个运行
    from datetime import UTC, datetime

    from screener.models import ScreenerRun

    run = ScreenerRun(
        criteria_hash="h", criteria_text="x", status="completed",
        created_at=datetime(2026, 10, 24, 8, 0, tzinfo=UTC),
    )
    test_session.add(run)
    await test_session.flush()
    portfolio.run_id = run.id
    test_session.add(portfolio)
    for ticker, close in (("AAA", 20.0), ("BBB", 10.0)):
        test_session.add(
            StockPrice(
                ticker=ticker, date=dt.date(2026, 10, 23), open=close,
                high=close, low=close, close=close, volume=1000.0,
            )
        )
    await test_session.commit()

    resp = client.post(
        f"/api/v1/screener/portfolios/{portfolio.id}/rebalance",
        json={"tolerance": 0.01, "lot_size": 100},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["portfolio_id"] == str(portfolio.id)
    assert data["summary"]["sells"] == 1 and data["summary"]["buys"] == 1
    assert {h["ticker"] for h in data["holdings"]} == {"AAA", "BBB"}

    missing = client.post(
        "/api/v1/screener/portfolios/00000000-0000-0000-0000-000000000000/rebalance",
        json={},
    )
    assert missing.status_code == 404
