"""Price service — query and ingest stock price data.

Data sources (3-layer fallback):
  1. PostgreSQL (already ingested data)
  2. Akshare MySQL (A-stocks, Layer 1)
  3. Local akshare subprocess (Layer 2, Tencent/Sina)
  4. Cloud MCP (Layer 3, 8.137.104.120)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import and_, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter
from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import (
    fetch_prices_via_mcp_cloud,
    is_a_stock,
    run_akshare,
    tx_symbol,
)
from market.models import StockPrice


class PriceService:
    """Stock price queries and ingestion with 3-layer fallback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self._mysql: AkshareMySQLAdapter | None = None

    async def _get_mysql(self) -> AkshareMySQLAdapter:
        if self._mysql is None:
            self._mysql = AkshareMySQLAdapter()
        return self._mysql

    # ── Query ──────────────────────────────────────────────────────

    async def get_prices(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[StockPrice]:
        """Get prices — PG first, MySQL for A-stocks, akshare for HK/all."""
        ticker_upper = ticker.upper()
        result: list[StockPrice] | None = None

        # Layer 1: PostgreSQL cache
        result = await self._get_prices_from_pg(ticker_upper, start_date, end_date, limit)
        if result:
            return await self._record_and_return(ticker, result)

        # Layer 2: MySQL for A-stocks
        if is_a_stock(ticker):
            try:
                result = await self._get_prices_from_mysql(ticker, start_date, end_date, limit)
                if result:
                    return await self._record_and_return(ticker, result)
            except Exception:
                logger.warning("Failed to fetch prices from MySQL for %s", ticker)

        # Layer 3: akshare subprocess (A-stock fallback + HK/all)
        try:
            fetched, _warns = await self.fetch_akshare(ticker)
            if fetched:
                await self.upsert_prices(ticker, fetched)
                result = await self._get_prices_from_pg(ticker_upper, start_date, end_date, limit)
                if result:
                    return await self._record_and_return(ticker, result)
        except Exception:
            logger.warning("Failed to fetch prices from akshare for %s", ticker)

        return []

    async def _record_and_return(
        self, ticker: str, prices: list[StockPrice]
    ) -> list[StockPrice]:
        """Record freshness and return prices."""
        from market.freshness_service import FreshnessService
        freshness = FreshnessService(self.session)
        await freshness.record_fetch(ticker, "prices", record_count=len(prices))
        return prices

    async def _get_prices_from_pg(
        self,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
    ) -> list[StockPrice]:
        stmt = select(StockPrice).where(StockPrice.ticker == ticker)
        if start_date:
            stmt = stmt.where(StockPrice.date >= start_date)
        if end_date:
            stmt = stmt.where(StockPrice.date <= end_date)
        stmt = stmt.order_by(desc(StockPrice.date)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_prices_from_mysql(
        self,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
    ) -> list[StockPrice]:
        mysql = await self._get_mysql()
        rows = await mysql.get_prices(ticker, start_date, end_date, limit)
        return [
            StockPrice(ticker=ticker, date=r.date, open=r.open, high=r.high,
                       low=r.low, close=r.close, volume=r.volume)
            for r in rows
        ]

    # ── Ingestion ──────────────────────────────────────────────────

    async def fetch_and_store_prices(
        self, ticker: str, provider: str = "akshare"
    ) -> tuple[int, list[str]]:
        """Fetch prices via akshare 3-layer chain and store in PostgreSQL."""
        from core.exceptions import ValidationError
        try:
            prices, warnings = await self.fetch_akshare(ticker)
        except Exception as e:
            raise ValidationError(f"Failed to fetch prices for {ticker}: {e}")
        count = await self.upsert_prices(ticker, prices)
        return count, warnings

    async def upsert_prices(self, ticker: str, prices: list[dict]) -> int:
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
                source="market", event_type="prices.ingested",
                entity_type="stock_price", entity_id=ticker,
                payload={"count": count, "ticker": ticker},
            )

        # Record freshness
        from market.freshness_service import FreshnessService
        freshness = FreshnessService(self.session)
        status = "ok" if count > 0 else "ok"
        await freshness.record_fetch(ticker, "prices", record_count=count, status=status)

        return count

    # ── 3-layer akshare fallback ────────────────────────────────────

    async def fetch_akshare(self, ticker: str) -> tuple[list[dict], list[str]]:
        """Fetch A-stock data — 3-layer fallback chain.

        Returns (prices, warnings) where warnings lists why each layer failed.
        """
        warnings: list[str] = []

        # Layer 1: akshare MySQL
        try:
            mysql = await self._get_mysql()
            rows = await mysql.get_prices(ticker, limit=520)
            if rows:
                logger.info("  [akshare] Layer 1 MySQL: %d rows for %s", len(rows), ticker)
                return [{
                    "date": r.date, "open": r.open, "high": r.high,
                    "low": r.low, "close": r.close, "volume": r.volume or 0,
                } for r in rows], []
            warnings.append("Layer 1 (MySQL): no data")
        except Exception as e:
            warnings.append(f"Layer 1 (MySQL): {e}")

        # Layer 2: local akshare (subprocess)
        try:
            rows = await self._fetch_akshare_local(ticker)
            if rows:
                logger.info("  [akshare] Layer 2 local: %d rows for %s", len(rows), ticker)
                return rows, []
            warnings.append("Layer 2 (Tencent/Sina): returned no data")
        except Exception as e:
            msg = f"Layer 2 (Tencent/Sina): {e}"
            warnings.append(msg)
            logger.warning("  [akshare] %s", msg)

        # Layer 3: cloud MCP
        try:
            rows = await fetch_prices_via_mcp_cloud(ticker)
            if rows:
                logger.info("  [akshare] Layer 3 cloud: %d rows for %s", len(rows), ticker)
                return rows, []
            warnings.append("Layer 3 (cloud MCP): no data")
        except Exception as e:
            msg = f"Layer 3 (cloud MCP): {e}"
            warnings.append(msg)
            logger.warning("  [akshare] %s", msg)

        logger.warning("  [akshare] All 3 layers failed for %s", ticker)
        return [], warnings

    async def _fetch_akshare_local(self, ticker: str) -> list[dict]:
        """Layer 2: run akshare locally via Tencent (A) or Sina (HK) data source."""
        import asyncio as _asyncio
        import json as _json

        is_hk = ticker.strip().isdigit() and len(ticker.strip()) in (4, 5)

        if is_hk:
            hk_symbol = ticker.zfill(5)
            code = (
                f'import json, sys\nimport akshare as ak\ntry:\n'
                f'    df = ak.stock_hk_daily(symbol="{hk_symbol}")\n'
                f'    if df is None or df.empty:\n        print("__R__:[]")\n'
                f'    else:\n        rows = []\n'
                f'        for _, row in df.iterrows():\n'
                f'            rows.append({{"date": str(row["date"])[:10],\n'
                f'                "open": float(row["open"]) if row["open"] == row["open"] else None,\n'
                f'                "high": float(row["high"]) if row["high"] == row["high"] else None,\n'
                f'                "low": float(row["low"]) if row["low"] == row["low"] else None,\n'
                f'                "close": float(row["close"]) if row["close"] == row["close"] else None,\n'
                f'                "volume": float(row.get("volume", 0) or 0)}})\n'
                f'        print("__R__:" + json.dumps(rows, ensure_ascii=False))\n'
                f'except Exception as e:\n'
                f'    print("__E__:" + str(e), file=sys.stderr)\n'
            )
        else:
            tx_sym = tx_symbol(ticker)
            code = (
                f'import json, sys\nimport akshare as ak\ntry:\n'
                f'    df = ak.stock_zh_a_hist_tx(symbol="{tx_sym}", start_date="19000101", end_date="20500101")\n'
                f'    if df is None or df.empty:\n        print("__R__:[]")\n'
                f'    else:\n        rows = []\n'
                f'        for _, row in df.iterrows():\n'
                f'            rows.append({{"date": str(row["date"])[:10],\n'
                f'                "open": float(row["open"]) if row["open"] == row["open"] else None,\n'
                f'                "high": float(row["high"]) if row["high"] == row["high"] else None,\n'
                f'                "low": float(row["low"]) if row["low"] == row["low"] else None,\n'
                f'                "close": float(row["close"]) if row["close"] == row["close"] else None,\n'
                f'                "volume": float(row.get("amount", 0) or 0)}})\n'
                f'        print("__R__:" + json.dumps(rows, ensure_ascii=False))\n'
                f'except Exception as e:\n'
                f'    print("__E__:" + str(e), file=sys.stderr)\n'
            )

        stdout = await _asyncio.to_thread(run_akshare, code)
        if not stdout:
            return []
        for line in stdout.splitlines():
            if line.startswith("__R__:"):
                data = _json.loads(line[6:])
                for r in data:
                    r["date"] = r["date"][:10] if "T" in str(r["date"]) else str(r["date"])
                    from datetime import date as _date
                    r["date"] = _date.fromisoformat(r["date"])
                return data
        return []

    # ── yfinance fallback ───────────────────────────────────────────

    async def fetch_yfinance(self, ticker: str) -> list[dict]:
        """Fetch prices via yfinance (US stocks, needs proxy)."""
        import yfinance as yf
        import asyncio
        import os

        yf_ticker = ticker
        if is_a_stock(ticker):
            yf_ticker = f"{ticker}.SS" if ticker.startswith("6") else f"{ticker}.SZ"

        def _fetch():
            for _var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                          "ftp_proxy", "FTP_PROXY", "all_proxy", "ALL_PROXY"):
                os.environ.pop(_var, None)
            stock = yf.Ticker(yf_ticker)
            from datetime import date as _d, timedelta as _td
            end = _d.today()
            start = end - _td(days=400)
            hist = stock.history(start=start.isoformat(), end=end.isoformat())
            results = []
            for idx, row in hist.iterrows():
                close = float(row["Close"])
                if close != close:
                    continue
                results.append({
                    "date": idx.date(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": close,
                    "volume": int(row["Volume"]),
                })
            return results

        return await asyncio.to_thread(_fetch)
