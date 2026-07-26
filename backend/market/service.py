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
        """Get prices — PG first, MySQL for A-stocks, akshare for HK/all."""
        ticker_upper = ticker.upper()

        # PostgreSQL (ingested data)
        pg_prices = await self._get_prices_from_pg(
            ticker_upper, start_date, end_date, limit
        )
        if pg_prices:
            return pg_prices

        # A-stocks → MySQL
        if _is_a_stock(ticker):
            try:
                return await self._get_prices_from_mysql(
                    ticker, start_date, end_date, limit
                )
            except Exception:
                pass

        # Non-A (HK stocks like 1810) → try fetch via akshare
        try:
            fetched, _warns = await self._fetch_akshare(ticker)
            if fetched:
                # Store to PG for next time
                await self.upsert_prices(ticker, fetched)
                # Query back with proper sorting
                return await self._get_prices_from_pg(
                    ticker_upper, start_date, end_date, limit
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
        """Get financial metrics — PG first, MySQL for A-stocks, akshare for HK."""
        ticker_upper = ticker.upper()

        # PostgreSQL first
        pg_metrics = await self._get_financials_from_pg(
            ticker_upper, metric, fiscal_year
        )
        if pg_metrics:
            return pg_metrics

        # A-stocks → MySQL
        if _is_a_stock(ticker):
            try:
                return await self._get_financials_from_mysql(
                    ticker, metric, fiscal_year
                )
            except Exception:
                pass

        # Non-A → try akshare fetch (HK stocks via eastmoney HK API)
        try:
            fetched = await self._fetch_akshare_financials(ticker)
            if fetched:
                await self.upsert_financials(ticker, fetched)
                # Query back
                return await self._get_financials_from_pg(
                    ticker_upper, metric, fiscal_year
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
        """Search stocks by code or name — MySQL (A-stocks) + PostgreSQL (all)."""
        results: list[dict] = []
        seen = set()

        # PostgreSQL: search Companies table (A, HK, US stocks)
        from company.models import Company
        stmt = select(Company).where(
            (Company.ticker.ilike(f"%{query}%"))
            | (Company.name.ilike(f"%{query}%"))
        ).limit(limit)
        rows = await self.session.execute(stmt)
        for c in rows.scalars().all():
            key = c.ticker.upper()
            if key not in seen:
                seen.add(key)
                results.append({"symbol": c.ticker, "name": c.name})

        # MySQL: search akshare stock_name_entity (A-stocks)
        try:
            mysql = await self._get_mysql()
            mysql_results = await mysql.search_stocks(query, limit)
            for r in mysql_results:
                key = r.get("symbol", "").upper()
                if key not in seen:
                    seen.add(key)
                    results.append(r)
        except Exception:
            pass

        return results[:limit]

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
    ) -> tuple[int, list[str]]:
        """Fetch prices via akshare 3-layer chain and store in PostgreSQL.

        Returns (count, warnings).
        """
        try:
            prices, warnings = await self._fetch_akshare(ticker)
        except Exception as e:
            raise ValidationError(
                f"Failed to fetch prices for {ticker}: {e}"
            )

        count = await self.upsert_prices(ticker, prices)
        return count, warnings

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

    async def upsert_financials(
        self, ticker: str, metrics: list[FinancialMetric]
    ) -> int:
        """Bulk upsert financial metrics into PostgreSQL."""
        count = 0
        for m in metrics:
            existing = await self.session.execute(
                select(FinancialMetric).where(
                    FinancialMetric.ticker == ticker.upper(),
                    FinancialMetric.fiscal_year == m.fiscal_year,
                    FinancialMetric.fiscal_period == m.fiscal_period,
                    FinancialMetric.metric_name == m.metric_name,
                )
            )
            if existing.scalar_one_or_none():
                continue
            self.session.add(FinancialMetric(
                ticker=ticker.upper(),
                fiscal_year=m.fiscal_year,
                fiscal_period=m.fiscal_period,
                metric_name=m.metric_name,
                metric_value=m.metric_value,
            ))
            count += 1

        if count:
            await self.session.flush()
            await self.events.record(
                source="market",
                event_type="financials.ingested",
                entity_type="financial_metric",
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

    async def _fetch_akshare(self, ticker: str) -> tuple[list[dict], list[str]]:
        """Fetch A-stock data — 3-layer fallback chain.

        Returns (prices, warnings) where warnings lists why each layer failed.
        """
        warnings: list[str] = []

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
                } for r in rows], []
            warnings.append("Layer 1 (MySQL): no data")
        except Exception as e:
            warnings.append(f"Layer 1 (MySQL): {e}")

        # Layer 2: local akshare (subprocess → uv run → akshare_mcp)
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

        # Layer 3: cloud MCP (HTTP → 8.137.104.120:8088)
        try:
            rows = await self._fetch_akshare_cloud(ticker)
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

    # ── HK-stock financials (via eastmoney HK API) ─────────────────────

    _HK_METRICS = [
        ("营业额", "revenue"),
        ("股东应占溢利", "net_income"),
        ("每股基本盈利", "eps"),
        ("毛利", "gross_profit"),
        ("经营溢利", "operating_profit"),
        ("研发费用", "rd_expense"),
    ]

    async def _fetch_akshare_financials(self, ticker: str) -> list[FinancialMetric]:
        """Fetch HK-stock financial data via akshare (eastmoney HK API)."""
        import akshare as ak
        import asyncio as _asyncio
        from datetime import datetime as _datetime

        # HK stock codes need leading-zero padding (1810 → 01810)
        hk_symbol = ticker.zfill(5)

        def _fetch():
            df = ak.stock_financial_hk_report_em(
                stock=hk_symbol, symbol="利润表", indicator="年度"
            )
            results: list[FinancialMetric] = []
            for cn_name, en_name in self._HK_METRICS:
                subset = df[df["STD_ITEM_NAME"] == cn_name]
                for _, row in subset.iterrows():
                    report_date = row["REPORT_DATE"]
                    # Can be string "2025-12-31" or datetime
                    if isinstance(report_date, str):
                        year = int(report_date[:4])
                    else:
                        year = report_date.year
                    value = float(row["AMOUNT"])
                    results.append(FinancialMetric(
                        ticker=ticker,
                        fiscal_year=year,
                        fiscal_period="Annual",
                        metric_name=en_name,
                        metric_value=value,
                    ))
            return results

        return await _asyncio.to_thread(_fetch)

    # ── Company profile fetch (cninfo for A, eastmoney HK for HK) ──────

    async def fetch_and_store_company_profile(self, ticker: str) -> dict:
        """Fetch company profile data and update the Company record in PG."""
        import akshare as ak
        import asyncio as _asyncio
        from company.models import Company
        from sqlalchemy import update as sql_update

        profile: dict[str, str | int | None] = {}
        is_hk = ticker.strip().isdigit() and len(ticker.strip()) in (4, 5)

        def _fetch_a():
            df = ak.stock_profile_cninfo(symbol=ticker)
            if df is None or df.empty:
                return {}
            row = df.iloc[0]
            cn_name = str(row.get("公司名称", ""))
            return {
                "name": cn_name if cn_name else None,
                "sector": row.get("所属行业"),
                "industry": row.get("所属行业"),
                "description": str(row.get("机构简介", ""))[:2000] if row.get("机构简介") else None,
                "website": row.get("官方网站"),
                "headquarters": row.get("办公地址"),
                "founded_year": int(str(row.get("成立日期", ""))[:4]) if row.get("成立日期") else None,
            }

        def _fetch_hk():
            hk_sym = ticker.zfill(5)
            df = ak.stock_hk_company_profile_em(symbol=hk_sym)
            if df is None or df.empty:
                return {}
            row = df.iloc[0]
            emp_raw = row.get("员工人数")
            try:
                employees = int(emp_raw)
            except (ValueError, TypeError):
                employees = None
            hk_name = str(row.get("公司名称", ""))
            return {
                "name": hk_name if hk_name else None,
                "sector": row.get("所属行业"),
                "industry": row.get("所属行业"),
                "description": str(row.get("公司介绍", ""))[:2000] if row.get("公司介绍") else None,
                "website": row.get("公司网址"),
                "headquarters": row.get("办公地址"),
                "founded_year": int(str(row.get("公司成立日期", ""))[:4]) if row.get("公司成立日期") else None,
                "employees": employees,
            }

        try:
            profile = await _asyncio.to_thread(_fetch_hk if is_hk else _fetch_a)
        except Exception as e:
            logger.warning("  [profile] fetch failed for %s: %s", ticker, e)
            return {}

        if not profile:
            return profile

        # Update Company record in PG
        update_data = {k: v for k, v in profile.items() if v is not None}
        if update_data:
            stmt = (
                sql_update(Company)
                .where(Company.ticker == ticker)
                .values(**update_data)
            )
            await self.session.execute(stmt)
            await self.session.flush()
            await self.events.record(
                source="market",
                event_type="company_profile.ingested",
                entity_type="company",
                entity_id=ticker,
                payload=update_data,
            )
            logger.info("  [profile] updated %s: %s", ticker, list(update_data.keys()))

        return profile

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
        """Layer 2: run akshare locally via Tencent (A) or Sina (HK) data source."""
        import asyncio as _asyncio
        import json as _json
        from datetime import date as _date

        is_hk = ticker.strip().isdigit() and len(ticker.strip()) in (4, 5)

        if is_hk:
            hk_symbol = ticker.zfill(5)
            code = f"""
import json, sys
import akshare as ak
try:
    df = ak.stock_hk_daily(symbol='{hk_symbol}')
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
                "volume": float(row.get("volume", 0) or 0),
            }})
        print("__R__:" + json.dumps(rows, ensure_ascii=False))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""
        else:
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
