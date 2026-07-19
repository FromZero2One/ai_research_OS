"""Market Center service — data sourced from akshare MCP MySQL (primary) + yfinance (fallback).

Data flow:
  1. Chinese A-stocks (digit symbols like 600519) → akshare MySQL (腾讯数据源，稳定)
  2. US stocks (letter symbols like AAPL) → yfinance (需代理)
  3. Financial metrics → akshare MySQL stock_yjbb_em
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter
from core.event_service import EventLogger
from core.exceptions import ValidationError
from market.models import FinancialMetric, StockPrice


def _is_a_stock(ticker: str) -> bool:
    """Check if ticker is a Chinese A-stock (all digits, 6 chars)."""
    return ticker.strip().isdigit() and len(ticker.strip()) == 6


class MarketService:
    """Market data — hybrid source: akshare MySQL (A-stocks) + yfinance (US)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self._mysql: AkshareMySQLAdapter | None = None

    async def _get_mysql(self) -> AkshareMySQLAdapter:
        if self._mysql is None:
            self._mysql = AkshareMySQLAdapter()
        return self._mysql

    # ── Stock Prices ──────────────────────────────────────────────

    async def get_prices(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[StockPrice]:
        """Get prices — from MySQL for A-stocks, else from PostgreSQL."""
        ticker_upper = ticker.upper()

        # For A-stocks, try MySQL first
        if _is_a_stock(ticker):
            return await self._get_prices_from_mysql(
                ticker, start_date, end_date, limit
            )

        # For US stocks / others, query PostgreSQL (may have been ingested)
        return await self._get_prices_from_pg(
            ticker_upper, start_date, end_date, limit
        )

    async def _get_prices_from_mysql(
        self,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
    ) -> list[StockPrice]:
        """Fetch from akshare MySQL and convert to StockPrice objects."""
        mysql = await self._get_mysql()
        rows = await mysql.get_prices(ticker, start_date, end_date, limit)

        # Get name for display
        name = await mysql.get_name(ticker)

        prices = []
        for r in rows:
            sp = StockPrice(
                ticker=ticker,
                date=r.date,
                open=r.open,
                high=r.high,
                low=r.low,
                close=r.close,
                volume=r.volume,
            )
            prices.append(sp)
        return prices

    async def _get_prices_from_pg(
        self,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
    ) -> list[StockPrice]:
        """Query from PostgreSQL (previously ingested data)."""
        stmt = select(StockPrice).where(StockPrice.ticker == ticker)
        if start_date:
            stmt = stmt.where(StockPrice.date >= start_date)
        if end_date:
            stmt = stmt.where(StockPrice.date <= end_date)
        stmt = stmt.order_by(desc(StockPrice.date)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Financial Metrics ─────────────────────────────────────────

    async def get_financials(
        self,
        ticker: str,
        metric: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[FinancialMetric]:
        """Get financial metrics — MySQL for A-stocks, PG otherwise."""
        ticker_upper = ticker.upper()

        if _is_a_stock(ticker):
            return await self._get_financials_from_mysql(
                ticker, metric, fiscal_year
            )

        return await self._get_financials_from_pg(
            ticker_upper, metric, fiscal_year
        )

    async def _get_financials_from_mysql(
        self, ticker: str, metric: str | None, fiscal_year: int | None
    ) -> list[FinancialMetric]:
        mysql = await self._get_mysql()
        rows = await mysql.get_financials(ticker, fiscal_year)

        results: list[FinancialMetric] = []
        for row in rows:
            for m_name, m_value in row.metrics.items():
                if metric and m_name != metric:
                    continue
                results.append(FinancialMetric(
                    ticker=ticker,
                    fiscal_year=row.fiscal_year,
                    fiscal_period=row.fiscal_period,
                    metric_name=m_name,
                    metric_value=m_value,
                ))
        return results

    async def _get_financials_from_pg(
        self, ticker: str, metric: str | None, fiscal_year: int | None
    ) -> list[FinancialMetric]:
        stmt = select(FinancialMetric).where(
            FinancialMetric.ticker == ticker
        )
        if metric:
            stmt = stmt.where(FinancialMetric.metric_name == metric)
        if fiscal_year:
            stmt = stmt.where(FinancialMetric.fiscal_year == fiscal_year)
        stmt = stmt.order_by(
            FinancialMetric.fiscal_year.desc(),
            FinancialMetric.fiscal_period,
        ).limit(500)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Stock Search ──────────────────────────────────────────────

    async def search_stocks(
        self, query: str, limit: int = 20
    ) -> list[dict]:
        """Search A-stocks by name or symbol from MySQL."""
        mysql = await self._get_mysql()
        return await mysql.search_stocks(query, limit)

    async def get_stock_info(self, ticker: str) -> dict | None:
        """Get stock basic info + latest valuation."""
        if not _is_a_stock(ticker):
            return None

        mysql = await self._get_mysql()
        name = await mysql.get_name(ticker)
        valuation = await mysql.get_valuation(ticker)

        # Get latest price
        prices = await mysql.get_prices(ticker, limit=1)
        latest_price = prices[0].close if prices else None

        return {
            "ticker": ticker,
            "name": name,
            "latest_price": latest_price,
            "valuation": valuation,
            "source": "akshare_mysql",
        }

    async def list_available_symbols(self, limit: int = 100) -> list[dict]:
        """List all A-stocks with K-line data available."""
        mysql = await self._get_mysql()
        symbols = await mysql.list_symbols(limit)
        result = []
        for sym in symbols:
            name = await mysql.get_name(sym)
            result.append({"symbol": sym, "name": name})
        return result

    # ── External data ingestion (yfinance, kept as fallback) ──────

    async def fetch_and_store_prices(
        self, ticker: str, provider: str = "yfinance"
    ) -> int:
        """Fetch prices from external provider, store in DB.

        Only used for US stocks that aren't in the MySQL database.
        """
        try:
            if provider == "yfinance":
                prices = await self._fetch_yfinance(ticker)
            else:
                prices = await self._fetch_akshare(ticker)
        except Exception as e:
            raise ValidationError(
                f"Failed to fetch prices for {ticker}: {e}"
            )

        return await self.upsert_prices(ticker, prices)

    async def upsert_prices(
        self, ticker: str, prices: list[dict]
    ) -> int:
        """Bulk upsert stock prices into PostgreSQL."""
        count = 0
        for row in prices:
            existing = await self.session.execute(
                select(StockPrice).where(
                    StockPrice.ticker == ticker.upper(),
                    StockPrice.date == row["date"],
                )
            )
            if existing.scalar_one_or_none():
                continue

            self.session.add(StockPrice(
                ticker=ticker.upper(),
                date=row["date"],
                open=row.get("open"),
                high=row.get("high"),
                low=row.get("low"),
                close=row.get("close"),
                volume=row.get("volume"),
                adjusted_close=row.get("adjusted_close"),
            ))
            count += 1

        if count:
            await self.session.flush()
            await self.events.record(
                source="market",
                event_type="prices.ingested",
                entity_type="stock_price",
                entity_id=ticker,
                payload={"count": count, "ticker": ticker},
            )
        return count

    async def _fetch_yfinance(self, ticker: str) -> list[dict]:
        import yfinance as yf
        import asyncio

        def _fetch():
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1y")
            results = []
            for idx, row in hist.iterrows():
                results.append({
                    "date": idx.date(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                })
            return results

        return await asyncio.to_thread(_fetch)

    async def _fetch_akshare(self, ticker: str) -> list[dict]:
        import akshare as ak
        import asyncio

        def _fetch():
            df = ak.stock_zh_a_hist(symbol=ticker, period="daily")
            results = []
            for _, row in df.iterrows():
                results.append({
                    "date": row["日期"].date()
                    if hasattr(row["日期"], "date") else row["日期"],
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": float(row["成交量"]),
                })
            return results

        return await asyncio.to_thread(_fetch)
