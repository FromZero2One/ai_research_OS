"""backtest_data 数据准备层单测 — 外部 MySQL 日线去重透传、历史财务按期补拉。"""

from __future__ import annotations

import datetime as dt
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from market.models import FinancialMetric, StockPrice
from screener.backtest_data import (
    ensure_financial_periods,
    fetch_daily_from_mysql,
    sync_daily_to_pg,
)


class FakeCursor:
    """预置行查询 fake（含同票同日重复行）。"""

    def __init__(self, rows: list[tuple]):
        self.rows = rows
        self.executed: list[tuple] = []

    def execute(self, sql: str, params: tuple | None = None) -> None:
        self.executed.append((sql, params))

    def fetchall(self) -> list[tuple]:
        return self.rows

    def close(self) -> None:
        pass

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class FakeConn:
    def __init__(self, cursor: FakeCursor):
        self._cursor = cursor

    def cursor(self, **kw: Any) -> FakeCursor:
        return self._cursor

    def close(self) -> None:
        pass


async def _noop_sleep(seconds: float) -> None:
    return None


SPOT_ROWS = [
    # symbol, date, open, close, high, low, volume — 含一条重复行
    ("600519", dt.date(2021, 1, 4), 1800.0, 1806.75, 1810.0, 1795.0, 406318.0),
    ("600519", dt.date(2021, 1, 4), 1800.0, 1806.75, 1810.0, 1795.0, 406318.0),  # 重复
    ("600519", dt.date(2021, 1, 5), 1860.0, 1869.2, 1875.0, 1855.0, 129647.0),
    ("300750", dt.date(2021, 1, 4), 350.0, 355.0, 360.0, 348.0, 90000.0),
]


def _patch_pymysql(monkeypatch, rows: list[tuple]) -> FakeCursor:
    cursor = FakeCursor(rows)
    fake_mod = type("M", (), {})()
    fake_mod.connect = lambda **kw: FakeConn(cursor)
    monkeypatch.setitem(__import__("sys").modules, "pymysql", fake_mod)
    return cursor


class TestFetchDailyFromMysql:
    async def test_dedupes_and_sorts(self, monkeypatch):
        """同票同日重复行去重；按 (symbol, date) 升序。"""
        from core.config import settings

        monkeypatch.setattr(settings, "BACKTEST_MYSQL_URL", "mysql+pymysql://u:p@fakehost:3306/akshare")
        _patch_pymysql(monkeypatch, SPOT_ROWS)
        out = await fetch_daily_from_mysql(["600519", "300750"], dt.date(2021, 1, 1), dt.date(2021, 1, 31))
        assert set(out.keys()) == {"600519", "300750"}
        dates_519 = [r["date"] for r in out["600519"]]
        assert dates_519 == [dt.date(2021, 1, 4), dt.date(2021, 1, 5)]
        assert out["600519"][0]["close"] == 1806.75

    async def test_retry_on_transient_failure(self, monkeypatch):
        """逐只拉取：每只票一次查询，结果合并。"""
        from core.config import settings
        import screener.backtest_data as bd

        monkeypatch.setattr(settings, "BACKTEST_MYSQL_URL", "mysql+pymysql://u:p@fakehost:3306/akshare")
        calls: list[list[str]] = []

        def _fake_sync(url, tickers, start, end):
            calls.append(list(tickers))
            return [("600519", dt.date(2021, 1, 4), 1.0, 2.0, 3.0, 0.5, 10.0)] if tickers == ["600519"] else []

        monkeypatch.setattr(bd, "_fetch_daily_sync", _fake_sync)
        out = await fetch_daily_from_mysql(["600519", "300750", "000001"], dt.date(2021, 1, 1), dt.date(2021, 1, 31))
        assert calls == [["600519"], ["300750"], ["000001"]]
        assert out["600519"][0]["close"] == 2.0
        assert "300750" not in out

    async def test_retry_on_transient_failure(self, monkeypatch):
        """网络抖动重试：前两次抛错、第三次成功 → 最终拿到数据。"""
        from core.config import settings
        import screener.backtest_data as bd

        monkeypatch.setattr(settings, "BACKTEST_MYSQL_URL", "mysql+pymysql://u:p@fakehost:3306/akshare")
        calls = {"n": 0}

        def _flaky(url, tickers, start, end):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("(2003, timed out)")
            return [("600519", dt.date(2021, 1, 4), 1.0, 2.0, 3.0, 0.5, 10.0)]

        monkeypatch.setattr(bd, "_fetch_daily_sync", _flaky)
        monkeypatch.setattr(bd.asyncio, "sleep", _noop_sleep)
        out = await fetch_daily_from_mysql(["600519"], dt.date(2021, 1, 1), dt.date(2021, 1, 31))
        assert calls["n"] == 3
        assert out["600519"][0]["close"] == 2.0

    async def test_empty_result(self, monkeypatch):
        from core.config import settings

        monkeypatch.setattr(settings, "BACKTEST_MYSQL_URL", "mysql+pymysql://u:p@fakehost:3306/akshare")
        _patch_pymysql(monkeypatch, [])
        out = await fetch_daily_from_mysql(["600519"], dt.date(2021, 1, 1), dt.date(2021, 1, 31))
        assert out == {}


class TestSyncDailyToPg:
    async def test_rows_written_with_exact_prices(self, test_session: AsyncSession, monkeypatch):
        """灌库幂等（先删后插）；close 值透传不自造。"""
        daily = {
            "600519": [
                {"date": dt.date(2021, 1, 4), "open": 1800.0, "close": 1806.75, "high": 1810.0, "low": 1795.0, "volume": 406318.0},
                {"date": dt.date(2021, 1, 5), "open": 1860.0, "close": 1869.2, "high": 1875.0, "low": 1855.0, "volume": 129647.0},
            ],
        }
        n1 = await sync_daily_to_pg(test_session, daily)
        await test_session.flush()
        assert n1 == 2

        # 重灌同一批 → 行数不变（幂等）
        n2 = await sync_daily_to_pg(test_session, daily)
        await test_session.flush()
        assert n2 == 2

        rows = (await test_session.execute(select(StockPrice).where(StockPrice.ticker == "600519"))).scalars().all()
        assert len(rows) == 2
        by_date = {r.date: r for r in rows}
        assert by_date[dt.date(2021, 1, 4)].close == 1806.75
        assert by_date[dt.date(2021, 1, 5)].close == 1869.2


class TestEnsureFinancialPeriods:
    async def test_calls_ingest_for_missing_periods_only(self, test_session: AsyncSession, monkeypatch):
        """缺失报告期调 ingest；已有数据的期跳过。"""
        import screener.backtest_data as bd

        called: list[tuple[int, str]] = []

        async def _missing(db, periods):
            return {p for p in periods if p != (2024, "Q3")}  # 2024Q3 已有

        async def _ingest(db, date_str: str) -> int:
            called.append((int(date_str[:4]), bd._period_from_date_str(date_str)))
            return 1

        monkeypatch.setattr(bd, "_missing_periods", _missing)
        monkeypatch.setattr(bd, "_ingest_yjbb_for_period", _ingest)

        await ensure_financial_periods(test_session, [(2024, "Q3"), (2024, "Q4")])
        assert called == [(2024, "Q4")]

    async def test_single_period_failure_isolated(self, test_session: AsyncSession, monkeypatch):
        """单期拉取失败不阻塞其他期。"""
        import screener.backtest_data as bd

        called: list[str] = []

        async def _missing(db, periods):
            return set(periods)

        async def _ingest(db, date_str: str) -> int:
            if "2024" in date_str:
                raise RuntimeError("akshare down")
            called.append(date_str)
            return 1

        monkeypatch.setattr(bd, "_missing_periods", _missing)
        monkeypatch.setattr(bd, "_ingest_yjbb_for_period", _ingest)

        await ensure_financial_periods(test_session, [(2024, "Q4"), (2025, "Q1")])
        assert called == ["20250331"]
