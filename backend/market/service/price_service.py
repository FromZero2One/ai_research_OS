"""Price service — query and ingest stock price data.

Data sources (2-layer fallback):
  1. PostgreSQL cache (already ingested data)
  2. Local akshare subprocess (Tencent/Sina)
  3. Cloud MCP (configurable via AKSHARE_CLOUD_MCP_URL)
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import (
    build_akshare_env,
    fetch_prices_via_mcp_cloud,
    is_a_stock,
    run_akshare,
)
from market.domain import PriceEntry
from market.repositories import PriceRepository
from market.service.shared import record_freshness

_AKSHARE_PRICE_CODE_HK = (
    "import json, os, sys\nimport akshare as ak\ntry:\n"
    '    ticker = os.environ["AKSHARE_TICKER"]\n'
    "    symbol = ticker.zfill(5)\n"
    "    df = ak.stock_hk_daily(symbol=symbol)\n"
    '    if df is None or df.empty:\n        print("__R__:[]")\n'
    "    else:\n        rows = []\n"
    "        for _, row in df.iterrows():\n"
    '            rows.append({"date": str(row["date"])[:10],\n'
    '                "open": float(row["open"]) if row["open"] == row["open"] else None,\n'
    '                "high": float(row["high"]) if row["high"] == row["high"] else None,\n'
    '                "low": float(row["low"]) if row["low"] == row["low"] else None,\n'
    '                "close": float(row["close"]) if row["close"] == row["close"] else None,\n'
    '                "volume": float(row.get("volume", 0) or 0)})\n'
    '        print("__R__:" + json.dumps(rows, ensure_ascii=False))\n'
    "except Exception as e:\n"
    '    print("__E__:" + str(e), file=sys.stderr)\n'
)


_AKSHARE_PRICE_CODE_A = (
    "import json, os, sys\nimport akshare as ak\ntry:\n"
    '    ticker = os.environ["AKSHARE_TICKER"]\n'
    '    symbol = ("sh" if ticker.startswith("6") else "sz") + ticker\n'
    '    df = ak.stock_zh_a_hist_tx(symbol=symbol, start_date="19000101", end_date="20500101")\n'
    '    if df is None or df.empty:\n        print("__R__:[]")\n'
    "    else:\n        rows = []\n"
    "        for _, row in df.iterrows():\n"
    '            rows.append({"date": str(row["date"])[:10],\n'
    '                "open": float(row["open"]) if row["open"] == row["open"] else None,\n'
    '                "high": float(row["high"]) if row["high"] == row["high"] else None,\n'
    '                "low": float(row["low"]) if row["low"] == row["low"] else None,\n'
    '                "close": float(row["close"]) if row["close"] == row["close"] else None,\n'
    '                "volume": float(row.get("amount", 0) or 0)})\n'
    '        print("__R__:" + json.dumps(rows, ensure_ascii=False))\n'
    "except Exception as e:\n"
    '    print("__E__:" + str(e), file=sys.stderr)\n'
)


class PriceService:
    """Stock price queries and ingestion with 3-layer fallback."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.prices = PriceRepository(session)

    # ── Query ──────────────────────────────────────────────────────

    async def get_prices(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[PriceEntry]:
        """Get prices — PG cache first, akshare subprocess for misses."""
        ticker_upper = ticker.upper()

        # Layer 1: PostgreSQL cache — 不记录 freshness：读缓存不代表数据新鲜，
        # 刷新 checked_at 会让停牌/退市股在质量看板上永远显示 ok（掩盖陈旧）。
        result = await self._get_prices_from_pg(ticker_upper, start_date, end_date, limit)
        if result:
            return result

        # Layer 2: akshare subprocess (A-stock + HK/all) —
        # upsert_prices 内部已记录 freshness，这里读回缓存不再重复记录
        try:
            fetched, _warns = await self.fetch_akshare(ticker)
            if fetched:
                await self.upsert_prices(ticker, fetched)
                result = await self._get_prices_from_pg(ticker_upper, start_date, end_date, limit)
                if result:
                    return result
        except Exception:
            logger.warning("Failed to fetch prices from akshare for %s", ticker)

        return []

    async def _get_prices_from_pg(
        self,
        ticker: str,
        start_date: date | None,
        end_date: date | None,
        limit: int,
    ) -> list[PriceEntry]:
        return await self.prices.get_for_ticker(ticker, start_date, end_date, limit)

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

    async def upsert_prices(self, ticker: str, prices: list[dict] | list[PriceEntry]) -> int:
        """Bulk upsert stock prices into PostgreSQL."""
        entries = [p if isinstance(p, PriceEntry) else PriceEntry.from_row(p) for p in prices]
        count = await self.prices.upsert(ticker, entries)

        if count:
            await self.events.record(
                source="market",
                event_type="prices.ingested",
                entity_type="stock_price",
                entity_id=ticker,
                payload={"count": count, "ticker": ticker},
            )

        # Record freshness
        await record_freshness(self.session, ticker, "prices", record_count=count, status="ok")

        return count

    # ── 2-layer akshare fallback ────────────────────────────────────

    async def fetch_akshare(self, ticker: str) -> tuple[list[dict], list[str]]:
        """Fetch A-stock/HK data — 2-layer fallback chain.

        Returns (prices, warnings) where warnings lists why each layer failed.
        """
        warnings: list[str] = []

        # Layer 1: local akshare (subprocess, Tencent/Sina)
        try:
            rows_local = await self._fetch_akshare_local(ticker)
            if rows_local:
                logger.info(
                    "  [akshare] Layer 1 local: %d rows for %s",
                    len(rows_local),
                    ticker,
                )
                return rows_local, []
            warnings.append("Layer 1 (Tencent/Sina): returned no data")
        except Exception as e:
            msg = f"Layer 1 (Tencent/Sina): {e}"
            warnings.append(msg)
            logger.warning("  [akshare] %s", msg)

        # Layer 2: cloud MCP
        try:
            rows_cloud = await fetch_prices_via_mcp_cloud(ticker)
            if rows_cloud:
                logger.info(
                    "  [akshare] Layer 2 cloud: %d rows for %s",
                    len(rows_cloud),
                    ticker,
                )
                return rows_cloud, []
            warnings.append("Layer 2 (cloud MCP): no data")
        except Exception as e:
            msg = f"Layer 2 (cloud MCP): {e}"
            warnings.append(msg)
            logger.warning("  [akshare] %s", msg)

        logger.warning("  [akshare] All layers failed for %s", ticker)
        return [], warnings

    async def _fetch_akshare_local(self, ticker: str) -> list[dict]:
        """Layer 1: run akshare locally via Tencent (A) or Sina (HK) data source."""
        import asyncio as _asyncio
        import json as _json

        is_hk = ticker.strip().isdigit() and len(ticker.strip()) in (4, 5)

        if is_hk:
            code = _AKSHARE_PRICE_CODE_HK
        else:
            code = _AKSHARE_PRICE_CODE_A

        stdout = await _asyncio.to_thread(run_akshare, code, build_akshare_env(ticker))
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
        import asyncio

        import yfinance as yf

        yf_ticker = ticker
        if is_a_stock(ticker):
            yf_ticker = f"{ticker}.SS" if ticker.startswith("6") else f"{ticker}.SZ"

        def _fetch():
            from core.proxy_cleanup import clean_proxy_env

            # yfinance 走网络，剥离干扰代理（与 app 启动同一套逻辑，含 no_proxy 设置）
            clean_proxy_env()
            stock = yf.Ticker(yf_ticker)
            from datetime import date as _d
            from datetime import timedelta as _td

            end = _d.today()
            start = end - _td(days=400)
            hist = stock.history(start=start.isoformat(), end=end.isoformat())
            results = []
            for idx, row in hist.iterrows():
                close = float(row["Close"])
                if close != close:
                    continue
                results.append(
                    {
                        "date": idx.date(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": close,
                        "volume": int(row["Volume"]),
                    }
                )
            return results

        return await asyncio.to_thread(_fetch)
