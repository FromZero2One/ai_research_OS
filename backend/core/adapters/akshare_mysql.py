"""Akshare MCP MySQL adapter — reads stock data from the akshare MySQL database.

The akshare MCP server maintains its own MySQL database (hosted at
root@localhost:3306/akshare) with pre-collected A-stock market data.
This adapter provides read-only access to that database, replacing direct
yfinance/AKShare API calls that are blocked by the network proxy.

Tables used:
  - stock_zh_a_hist     : Daily K-line data (Tencent source, stable)
  - stock_yjbb_em       : Financial metrics (revenue, profit, ROE, etc.)
  - stock_value_em      : Valuation metrics (PE, PB, etc.)
  - stock_name_entity   : Symbol-to-name mapping

Usage:
    adapter = AkshareMySQLAdapter()
    prices = await adapter.get_prices("600519")
    metrics = await adapter.get_financials("000001")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class PriceRow:
    """Maps stock_zh_a_hist row to our StockPrice model."""
    ticker: str
    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None  # 成交额（元）
    adjusted_close: float | None = None


@dataclass
class FinancialRow:
    """Maps stock_yjbb_em row to our FinancialMetric model."""
    ticker: str
    fiscal_year: int
    fiscal_period: str
    metrics: dict[str, float | None] = field(default_factory=dict)


_DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "root",
    "database": "akshare",
    "charset": "utf8mb4",
}


class AkshareMySQLAdapter:
    """Read-only adapter for akshare MCP's MySQL database."""

    def __init__(self, config: dict | None = None) -> None:
        self._config = config or _DB_CONFIG
        self._conn: Any = None

    # ── Connection management ────────────────────────────────────────

    async def _get_conn(self):
        """Lazy connect — runs in thread pool to avoid blocking."""
        if self._conn is None:
            import pymysql
            conn = await asyncio.to_thread(
                pymysql.connect, **self._config
            )
            self._conn = conn
        return self._conn

    async def close(self):
        if self._conn:
            await asyncio.to_thread(self._conn.close)
            self._conn = None

    # ── Query helpers ────────────────────────────────────────────────

    async def _fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute SELECT and return list of dicts."""
        conn = await self._get_conn()
        return await asyncio.to_thread(self._fetch_all_sync, conn, sql, params)

    @staticmethod
    def _fetch_all_sync(conn, sql: str, params: tuple) -> list[dict]:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]

    # ── Public API ───────────────────────────────────────────────────

    async def get_prices(
        self,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[PriceRow]:
        """Query daily K-line data from stock_zh_a_hist."""
        sql = """
            SELECT `日期`, `开盘`, `收盘`, `最高`, `最低`, `成交额`, `数据来源`
            FROM stock_zh_a_hist
            WHERE symbol = %s
        """
        params: list[Any] = [symbol]

        if start_date:
            sql += " AND `日期` >= %s"
            params.append(start_date)
        if end_date:
            sql += " AND `日期` <= %s"
            params.append(end_date)

        sql += " ORDER BY `日期` DESC LIMIT %s"
        params.append(limit)

        rows = await self._fetch_all(sql, tuple(params))
        return [
            PriceRow(
                ticker=symbol,
                date=r["日期"],
                open=r.get("开盘"),
                high=r.get("最高"),
                low=r.get("最低"),
                close=r.get("收盘"),
                volume=r.get("成交额"),
            )
            for r in rows
        ]

    async def get_financials(
        self, symbol: str, fiscal_year: int | None = None
    ) -> list[FinancialRow]:
        """Query financial metrics from stock_yjbb_em.

        Each metric_name in the DB becomes a key in FinancialRow.metrics.
        """
        sql = """
            SELECT *
            FROM stock_yjbb_em
            WHERE `股票代码` = %s
        """
        params: list[Any] = [symbol]

        # Determine fiscal year from 最新公告日期
        if fiscal_year:
            sql += " AND YEAR(`最新公告日期`) = %s"
            params.append(fiscal_year)

        sql += " ORDER BY `最新公告日期` DESC"

        rows = await self._fetch_all(sql, tuple(params))

        METRIC_KEYS = [
            ("每股收益", "eps"),
            ("营业总收入-营业总收入", "revenue"),
            ("营业总收入-同比增长", "revenue_growth"),
            ("营业总收入-季度环比增长", "revenue_qoq"),
            ("净利润-净利润", "net_income"),
            ("净利润-同比增长", "net_income_growth"),
            ("净利润-季度环比增长", "net_income_qoq"),
            ("每股净资产", "bvps"),
            ("净资产收益率", "roe"),
            ("每股经营现金流量", "cfps"),
            ("销售毛利率", "gross_margin"),
        ]

        results: list[FinancialRow] = []
        for r in rows:
            report_date = r.get("最新公告日期")
            year = report_date.year if report_date else 0
            # Infer period from Q1/Q2/Q3/Annual based on month
            month = report_date.month if report_date else 1
            if month >= 10:
                period = "Q3"
            elif month >= 7:
                period = "Q2"
            elif month >= 4:
                period = "Q1"
            else:
                period = "Annual"

            metrics = {}
            for cn_key, en_key in METRIC_KEYS:
                val = r.get(cn_key)
                if val is not None:
                    metrics[en_key] = float(val)

            results.append(FinancialRow(
                ticker=symbol,
                fiscal_year=year,
                fiscal_period=period,
                metrics=metrics,
            ))

        return results

    async def get_valuation(
        self, symbol: str
    ) -> dict[str, Any] | None:
        """Query valuation data from stock_value_em.

        Returns latest PE, PB, PS, PCF ratios if available.
        """
        sql = """
            SELECT *
            FROM stock_value_em
            WHERE symbol = %s
            ORDER BY `数据日期` DESC
            LIMIT 1
        """
        rows = await self._fetch_all(sql, (symbol,))
        if not rows:
            return None
        r = rows[0]
        return {
            "ticker": symbol,
            "pe": r.get("市盈率-动态"),
            "pb": r.get("市净率"),
            "ps": r.get("市销率"),
            "pcf": r.get("市现率"),
            "date": r.get("数据日期"),
        }

    async def search_stocks(
        self, query: str, limit: int = 20
    ) -> list[dict]:
        """Search stocks by symbol or name from stock_name_entity."""
        sql = """
            SELECT symbol, stock_name AS name
            FROM stock_name_entity
            WHERE symbol LIKE %s OR stock_name LIKE %s
            LIMIT %s
        """
        like = f"%{query}%"
        rows = await self._fetch_all(sql, (like, like, limit))
        return [{"symbol": r["symbol"], "name": r["name"]} for r in rows]

    async def list_symbols(self, limit: int = 50) -> list[str]:
        """List all symbols that have K-line data."""
        sql = """
            SELECT DISTINCT symbol FROM stock_zh_a_hist ORDER BY symbol LIMIT %s
        """
        rows = await self._fetch_all(sql, (limit,))
        return [r["symbol"] for r in rows]

    async def get_name(self, symbol: str) -> str | None:
        """Get Chinese name for a symbol."""
        sql = """
            SELECT stock_name FROM stock_name_entity WHERE symbol = %s LIMIT 1
        """
        rows = await self._fetch_all(sql, (symbol,))
        return rows[0]["stock_name"] if rows else None
