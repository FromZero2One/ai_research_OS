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
from core.logging import logger
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

        # First try PostgreSQL (real yfinance data), fall back to MySQL
        pg_prices = await self._get_prices_from_pg(
            ticker_upper, start_date, end_date, limit
        )
        if pg_prices:
            return pg_prices

        # For A-stocks, try MySQL as fallback
        if _is_a_stock(ticker):
            try:
                return await self._get_prices_from_mysql(
                    ticker, start_date, end_date, limit
                )
            except Exception:
                pass

        return []

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

        # First try PostgreSQL (yfinance data), fall back to MySQL
        pg_metrics = await self._get_financials_from_pg(
            ticker_upper, metric, fiscal_year
        )
        if pg_metrics:
            return pg_metrics

        if _is_a_stock(ticker):
            try:
                return await self._get_financials_from_mysql(
                    ticker, metric, fiscal_year
                )
            except Exception:
                pass

        return []

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
        self, ticker: str, provider: str = "akshare"
    ) -> int:
        """Fetch prices via akshare 3-layer chain and store in PostgreSQL."""
        try:
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
        import os

        # Auto-add exchange suffix for A-stock tickers
        yf_ticker = ticker
        if _is_a_stock(ticker):
            # 6xxxxx → .SS (上交所), 0xxxxx/3xxxxx → .SZ (深交所)
            if ticker.startswith("6"):
                yf_ticker = f"{ticker}.SS"
            else:
                yf_ticker = f"{ticker}.SZ"

        def _fetch():
            # Strip proxy vars so yfinance can reach Yahoo Finance directly
            for _var in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                          "ftp_proxy", "FTP_PROXY", "all_proxy", "ALL_PROXY"):
                os.environ.pop(_var, None)
            stock = yf.Ticker(yf_ticker)
            # Use start/end dates instead of period to avoid cache flakiness
            from datetime import date as _d, timedelta as _td
            end = _d.today()
            start = end - _td(days=400)
            hist = stock.history(start=start.isoformat(), end=end.isoformat())
            results = []
            for idx, row in hist.iterrows():
                close = float(row["Close"])
                if close != close:  # skip NaN
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

    async def _fetch_akshare(self, ticker: str) -> list[dict]:
        """Fetch A-stock data — 4-layer fallback chain."""
        # Layer 1: akshare MySQL (fast, local)
        try:
            mysql = await self._get_mysql()
            rows = await mysql.get_prices(ticker, limit=520)
            if rows:
                logger.info("  [akshare] Layer 1 MySQL: %d rows for %s", len(rows), ticker)
                return [{
                    "date": r.date,
                    "open": r.open,
                    "high": r.high,
                    "low": r.low,
                    "close": r.close,
                    "volume": r.volume or 0,
                } for r in rows]
        except Exception:
            pass

        # Layer 2: local akshare (subprocess → uv run → akshare_mcp)
        try:
            rows = await self._fetch_akshare_local(ticker)
            if rows:
                logger.info("  [akshare] Layer 2 local: %d rows for %s", len(rows), ticker)
                return rows
        except Exception as e:
            logger.warning("  [akshare] Layer 2 failed: %s", e)

        # Layer 3: cloud MCP (HTTP → 8.137.104.120:8088)
        try:
            rows = await self._fetch_akshare_cloud(ticker)
            if rows:
                logger.info("  [akshare] Layer 3 cloud: %d rows for %s", len(rows), ticker)
                return rows
        except Exception as e:
            logger.warning("  [akshare] Layer 3 failed: %s", e)

        logger.warning("  [akshare] All 3 layers failed for %s", ticker)
        return []

    # ── Layer 2: local akshare (subprocess) ────────────────────────────

    @staticmethod
    def _run_akshare(code: str) -> str | None:
        """Run akshare Python code in akshare_mcp venv and return stdout."""
        import os as _os, subprocess as _sp
        AKSHARE_MCP_DIR = _os.getenv("AKSHARE_MCP_DIR", "/home/wsm/codes/akshare_mcp")
        # Minimal env — env -i style — to dodge any inherited proxy
        env = {
            "HOME": _os.environ.get("HOME", ""),
            "PATH": _os.environ.get("PATH", ""),
            "USER": _os.environ.get("USER", ""),
            "NO_PROXY": "localhost,127.0.0.0/8,::1",
            "no_proxy": "localhost,127.0.0.0/8,::1",
        }
        try:
            result = _sp.run(
                ["uv", "run", "--directory", AKSHARE_MCP_DIR, "python", "-c", code],
                capture_output=True, text=True, timeout=60, env=env,
            )
            if result.returncode != 0:
                return None
            return result.stdout
        except Exception:
            return None

    @staticmethod
    def _tx_symbol(ticker: str) -> str:
        """Convert 6-digit A-stock code to Tencent format (sz/sh prefix)."""
        return f"sh{ticker}" if ticker.startswith("6") else f"sz{ticker}"

    async def _fetch_akshare_local(self, ticker: str) -> list[dict]:
        """Layer 2: run akshare locally via Tencent data source (stable)."""
        import asyncio as _asyncio
        import json as _json
        from datetime import date as _date

        tx_sym = self._tx_symbol(ticker)
        code = f"""
import json, sys
import akshare as ak
try:
    df = ak.stock_zh_a_hist_tx(symbol='{tx_sym}', start_date='19000101', end_date='20500101')
    if df is None or df.empty:
        print("__R__:[]")
    else:
        rows = []
        for _, row in df.iterrows():
            rows.append({{
                "date": str(row["date"])[:10],
                "open": float(row["open"]) if row["open"] == row["open"] else None,
                "high": float(row["high"]) if row["high"] == row["high"] else None,
                "low": float(row["low"]) if row["low"] == row["low"] else None,
                "close": float(row["close"]) if row["close"] == row["close"] else None,
                "volume": float(row.get("amount", 0) or 0),
            }})
        print("__R__:" + json.dumps(rows, ensure_ascii=False))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""
        stdout = await _asyncio.to_thread(self._run_akshare, code)
        if not stdout:
            return []
        for line in stdout.splitlines():
            if line.startswith("__R__:"):
                data = _json.loads(line[6:])
                # Convert date strings back to date objects
                for r in data:
                    r["date"] = r["date"][:10] if "T" in str(r["date"]) else str(r["date"])
                    r["date"] = _date.fromisoformat(r["date"])
                return data
        return []

    # ── Layer 3: cloud MCP (HTTP) ─────────────────────────────────────

    async def _fetch_akshare_cloud(self, ticker: str) -> list[dict]:
        """Layer 3: call cloud MCP server's stock_zh_a_hist tool."""
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client
        from mcp.types import TextContent
        from datetime import date as _date

        CLOUD_MCP_URL = "http://8.137.104.120:8088/mcp"

        http_client = httpx.AsyncClient(verify=False, timeout=30)
        try:
            async with streamable_http_client(CLOUD_MCP_URL, http_client=http_client) as (read, write, _get_id):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("stock_zh_a_hist", {
                        "symbol": ticker,
                        "period": "daily",
                        "adjust": "",
                    })
                    rows = []
                    for c in result.content:
                        if isinstance(c, TextContent):
                            rows.extend(self._parse_mcp_table(c.text))
                    if not rows:
                        return []

                    # Convert to upsert_prices format
                    prices = []
                    for r in rows:
                        date_str = r.get("日期", "")
                        if not date_str:
                            continue
                        prices.append({
                            "date": _date.fromisoformat(str(date_str)[:10]),
                            "open": self._to_float(r.get("开盘")),
                            "high": self._to_float(r.get("最高")),
                            "low": self._to_float(r.get("最低")),
                            "close": self._to_float(r.get("收盘")),
                            "volume": self._to_float(r.get("成交量", 0)) or 0,
                        })
                    return prices
        finally:
            await http_client.aclose()

    @staticmethod
    def _to_float(v) -> float | None:
        if v is None:
            return None
        try:
            return float(v)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _parse_mcp_table(text: str) -> list[dict]:
        """Parse pandas DataFrame text table → list[dict]."""
        lines = text.strip().split("\n")
        if len(lines) < 2:
            return []
        header_line = lines[0]
        headers = [h.strip() for h in header_line.split("  ") if h.strip()]
        results = []
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = [p for p in line.split("  ") if p.strip()]
            if parts and parts[0].isdigit():
                parts = parts[1:]
            if len(parts) == len(headers):
                results.append(dict(zip(headers, parts)))
            elif len(parts) > 0:
                row = {}
                for i, h in enumerate(headers):
                    row[h] = parts[i] if i < len(parts) else ""
                results.append(row)
        return results
