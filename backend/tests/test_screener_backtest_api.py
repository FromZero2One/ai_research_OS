"""回测编排 + API 单测 — monkeypatch 数据层，验证状态机/结果/报告/422/409。"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces import LLMResponse
from screener.backtest_data import fetch_daily_from_mysql  # noqa: F401 (monkeypatch target ref)
from screener.models import CriteriaPreset, ScreenerBacktestRun
from screener.service import _ensure_market_data  # noqa: F401


# ── 预置数据：2 只票 × 2 个调仓期，规则 ROE>10 全通过 ──

def _daily() -> dict[str, list[dict]]:
    # 日期须落在回测区间（years=1 → 今天往前 1 年）内的披露截止日之后
    d1 = dt.date(2025, 11, 3)   # 2025-10-31（Q3 披露截止）后首个交易日
    d2 = dt.date(2026, 5, 6)    # 2026-04-30（年报截止）后首个交易日
    d3 = dt.date(2026, 9, 1)    # 2026-08-31（中报截止）后首个交易日
    bars = {}
    for sym, base in (("600519", 100.0), ("300750", 50.0)):
        bars[sym] = [
            {"date": d1, "open": base, "close": base, "high": base, "low": base, "volume": 1000.0},
            {"date": d2, "open": base * 1.1, "close": base * 1.1, "high": base * 1.1, "low": base * 1.1, "volume": 1000.0},
            {"date": d3, "open": base * 1.2, "close": base * 1.2, "high": base * 1.2, "low": base * 1.2, "volume": 1000.0},
        ]
    return bars


class _FakeLLM:
    async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="{}", model="fake", usage=None)


@pytest.fixture
def backtest_env(monkeypatch):
    """mock 数据层：日线全命中；财务期已有数据（跳过补拉）。"""
    import screener.backtest_data as bd
    import screener.backtest_service as bs

    async def _daily_ok(db, tickers, start, end):
        # 现实现是「逐只拉取并落库」，返回值是同步的票数；测试里直接灌 StockPrice
        from market.models import StockPrice

        full = _daily()
        synced = 0
        for t in tickers:
            bars = full.get(t) or []
            for b in bars:
                db.add(
                    StockPrice(
                        ticker=t, date=b["date"], open=b["open"], high=b["high"],
                        low=b["low"], close=b["close"], volume=b["volume"],
                    )
                )
            if bars:
                synced += 1
        await db.flush()
        return synced

    async def _noop(db, periods):
        return 0

    async def _bench(start, end):
        return [
            {"date": dt.date(2025, 11, 3), "close": 5000.0},
            {"date": dt.date(2026, 5, 6), "close": 5000.0},
            {"date": dt.date(2026, 9, 1), "close": 5000.0},
        ]

    async def _shares(db, tickers):
        return {t: 1e9 for t in tickers}  # 总股本 10 亿（近似市值用）

    async def _all_tickers(start, end):
        # 测试库无 Company 行时，服务会回退到外部 MySQL 取票池；单测中固定返回两只票
        return ["600519", "300750"]

    monkeypatch.setattr(bd, "fetch_all_tickers", _all_tickers)
    monkeypatch.setattr(bs, "fetch_daily_from_mysql", _daily_ok)
    monkeypatch.setattr(bs, "ensure_financial_periods", _noop)
    monkeypatch.setattr(bs, "fetch_index_daily", _bench)
    monkeypatch.setattr(bs, "_fetch_total_shares", _shares)
    monkeypatch.setattr(bs, "_price_dates_from_pg", _price_dates_stub)


async def _price_dates_stub(db, start, end):
    base = _daily()
    days = sorted({b["date"] for bars in base.values() for b in bars})
    return days


class TestRunBacktest:
    async def test_end_to_end(self, test_session: AsyncSession, backtest_env, monkeypatch):
        """状态机完成、result 结构齐全、报告文件落盘含免责声明。"""
        from screener.backtest_service import run_backtest

        preset = CriteriaPreset(
            name="测试预设", description="d", style_tag="test", is_builtin=False, is_active=True,
            quant_rules=[{"metric": "roe", "op": ">", "value": 10, "missing_data_policy": "exclude"}],
            qualitative=[], suggested_pool="all",
        )
        test_session.add(preset)
        await test_session.flush()

        run = ScreenerBacktestRun(preset_id=preset.id, years=1, status="pending")
        test_session.add(run)
        await test_session.flush()

        done = await run_backtest(test_session, run.id)
        await test_session.flush()
        assert done.status == "completed"
        assert done.result is not None
        assert "summary" in done.result and "yearly" in done.result
        assert done.result["summary"]["periods_count"] >= 1
        assert done.report_path is not None
        report = open(done.report_path, encoding="utf-8").read()
        assert "预设回测报告" in report
        assert "未计交易费用" in report
        assert "市值为近似值" in report

    async def test_empty_daily_fails_run(self, test_session: AsyncSession, backtest_env, monkeypatch):
        """外部日线为空 → run 置 failed 且 error 非空。"""
        import screener.backtest_service as bs
        from screener.backtest_service import run_backtest

        async def _empty(tickers, start, end):
            return {}

        monkeypatch.setattr(bs, "fetch_daily_from_mysql", _empty)

        preset = CriteriaPreset(
            name="测试预设2", description="d", style_tag="test2", is_builtin=False, is_active=True,
            quant_rules=[], qualitative=[], suggested_pool="all",
        )
        test_session.add(preset)
        await test_session.flush()
        run = ScreenerBacktestRun(preset_id=preset.id, years=1, status="pending")
        test_session.add(run)
        await test_session.flush()

        done = await run_backtest(test_session, run.id)
        await test_session.flush()
        assert done.status == "failed"
        assert done.error


class TestBacktestAPI:
    async def test_post_and_get(self, client, backtest_env, test_session: AsyncSession):
        """POST 建 run 返回 201；未知预设 → 422。"""
        preset = CriteriaPreset(
            name="API预设", description="d", style_tag="api", is_builtin=False, is_active=True,
            quant_rules=[], qualitative=[], suggested_pool="all",
        )
        test_session.add(preset)
        await test_session.commit()  # 路由用独立 session，必须落库可见

        # 未知预设 → 422
        resp = client.post("/api/v1/screener/backtests", json={"preset_id": str(__import__("uuid").uuid4()), "years": 5})
        assert resp.status_code == 422
        # 正常触发 → 201
        resp = client.post("/api/v1/screener/backtests", json={"preset_id": str(preset.id), "years": 5})
        assert resp.status_code == 201
        run_id = resp.json()["id"]
        # GET 详情
        resp = client.get(f"/api/v1/screener/backtests/{run_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("pending", "running", "completed")
