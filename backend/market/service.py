"""Market Center service — data ingestion (AKShare/Yahoo) and queries."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from core.exceptions import ValidationError
from market.models import FinancialMetric, StockPrice


class MarketService:
    """Handles structured market data: prices, financials, macros."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    # ── Stock Prices ──────────────────────────────────────────────

    async def upsert_prices(
        self, ticker: str, prices: list[dict]
    ) -> int:
        """Bulk upsert stock prices. Returns count inserted."""
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

            self.session.add(
                StockPrice(
                    ticker=ticker.upper(),
                    date=row["date"],
                    open=row.get("open"),
                    high=row.get("high"),
                    low=row.get("low"),
                    close=row.get("close"),
                    volume=row.get("volume"),
                    adjusted_close=row.get("adjusted_close"),
                )
            )
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

    async def get_prices(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[StockPrice]:
        stmt = select(StockPrice).where(StockPrice.ticker == ticker.upper())
        if start_date:
            stmt = stmt.where(StockPrice.date >= start_date)
        if end_date:
            stmt = stmt.where(StockPrice.date <= end_date)
        stmt = stmt.order_by(desc(StockPrice.date)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Financial Metrics ─────────────────────────────────────────

    async def upsert_financials(
        self, ticker: str, metrics: list[dict]
    ) -> int:
        count = 0
        for row in metrics:
            existing = await self.session.execute(
                select(FinancialMetric).where(
                    FinancialMetric.ticker == ticker.upper(),
                    FinancialMetric.fiscal_year == row["fiscal_year"],
                    FinancialMetric.fiscal_period == row["fiscal_period"],
                    FinancialMetric.metric_name == row["metric_name"],
                )
            )
            if existing.scalar_one_or_none():
                continue

            self.session.add(
                FinancialMetric(
                    ticker=ticker.upper(),
                    fiscal_year=row["fiscal_year"],
                    fiscal_period=row["fiscal_period"],
                    metric_name=row["metric_name"],
                    metric_value=row.get("metric_value"),
                )
            )
            count += 1

        if count:
            await self.session.flush()
        return count

    async def get_financials(
        self,
        ticker: str,
        metric: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[FinancialMetric]:
        stmt = select(FinancialMetric).where(
            FinancialMetric.ticker == ticker.upper()
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

    # ── External data ingestion ───────────────────────────────────

    async def fetch_and_store_prices(
        self, ticker: str, provider: str = "yfinance"
    ) -> int:
        """Fetch prices from external provider, store in DB. Returns count."""
        try:
            if provider == "yfinance":
                prices = await self._fetch_yfinance(ticker)
            else:
                prices = await self._fetch_akshare(ticker)
        except Exception as e:
            raise ValidationError(f"Failed to fetch prices for {ticker}: {e}")

        return await self.upsert_prices(ticker, prices)

    async def _fetch_yfinance(self, ticker: str) -> list[dict]:
        import yfinance as yf

        # yfinance is synchronous — run in thread pool
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
                    "date": row["日期"].date() if hasattr(row["日期"], "date") else row["日期"],
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": float(row["成交量"]),
                })
            return results

        return await asyncio.to_thread(_fetch)
