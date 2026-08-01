"""Financial metrics service — query and ingest financial data.

A-stocks → Akshare MySQL (stock_yjbb_em)
HK stocks → akshare eastmoney HK API
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter
from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import is_a_stock
from market.domain import FinancialMetricEntry
from market.repositories import FinancialRepository

# HK-stock metric key mapping (Chinese → English)
HK_METRICS = [
    ("营业额", "revenue"),
    ("股东应占溢利", "net_income"),
    ("每股基本盈利", "eps"),
    ("毛利", "gross_profit"),
    ("经营溢利", "operating_profit"),
    ("研发费用", "rd_expense"),
]

_HK_FINANCIALS_CODE = """\
import json, os, sys
import akshare as ak
try:
    ticker = os.environ["AKSHARE_TICKER"]
    df = ak.stock_financial_hk_report_em(stock=ticker.zfill(5), symbol="利润表", indicator="年度")
    if df is None or df.empty:
        print("__R__:[]")
    else:
        wanted = {"营业额", "股东应占溢利", "每股基本盈利", "毛利", "经营溢利", "研发费用"}
        rows = []
        for cn_name in wanted:
            subset = df[df["STD_ITEM_NAME"] == cn_name]
            for _, row in subset.iterrows():
                rd = row["REPORT_DATE"]
                year = int(str(rd)[:4]) if isinstance(rd, str) else rd.year
                rows.append({"cn": cn_name, "year": year, "value": float(row["AMOUNT"])})
        print("__R__:" + json.dumps(rows, ensure_ascii=False, default=str))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""


class FinancialService:
    """Financial metrics — MySQL (A) / akshare (HK) with PG cache."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.repo = FinancialRepository(session)
        self._mysql: AkshareMySQLAdapter | None = None

    async def _get_mysql(self) -> AkshareMySQLAdapter:
        if self._mysql is None:
            self._mysql = AkshareMySQLAdapter()
        return self._mysql

    async def get_financials(
        self,
        ticker: str,
        metric: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[FinancialMetricEntry]:
        """Get financial metrics — PG first, MySQL for A-stocks, akshare for HK."""
        ticker_upper = ticker.upper()

        pg_metrics = await self.repo.get_for_ticker(ticker_upper, metric, fiscal_year)
        if pg_metrics:
            return pg_metrics

        if is_a_stock(ticker):
            try:
                return await self._get_financials_from_mysql(ticker, metric, fiscal_year)
            except Exception:
                logger.warning("Failed to fetch financials from MySQL for %s", ticker)
                pass

        # Non-A → try akshare HK API
        try:
            fetched = await self._fetch_akshare_financials(ticker)
            if fetched:
                await self.upsert_financials(ticker, fetched)
                return await self.repo.get_for_ticker(ticker_upper, metric, fiscal_year)
        except Exception:
            logger.warning("Failed to fetch financials from akshare HK for %s", ticker)
            pass

        return []

    async def _get_financials_from_mysql(
        self, ticker: str, metric: str | None, fiscal_year: int | None
    ) -> list[FinancialMetricEntry]:
        mysql = await self._get_mysql()
        rows = await mysql.get_financials(ticker, fiscal_year)

        results: list[FinancialMetricEntry] = []
        for row in rows:
            for m_name, m_value in row.metrics.items():
                if metric and m_name != metric:
                    continue
                results.append(
                    FinancialMetricEntry(
                        fiscal_year=row.fiscal_year,
                        fiscal_period=row.fiscal_period,
                        metric_name=m_name,
                        metric_value=m_value,
                    )
                )
        return results

    async def upsert_financials(self, ticker: str, metrics: list[FinancialMetricEntry]) -> int:
        """Bulk upsert financial metrics into PostgreSQL."""
        count = await self.repo.upsert(ticker, metrics)

        if count:
            await self.events.record(
                source="market",
                event_type="financials.ingested",
                entity_type="financial_metric",
                entity_id=ticker,
                payload={"count": count, "ticker": ticker},
            )

        # Record freshness
        from market.service.freshness_service import FreshnessService

        freshness = FreshnessService(self.session)
        await freshness.record_fetch(ticker, "financials", record_count=count, status="ok")

        return count

    async def _fetch_akshare_financials(self, ticker: str) -> list[FinancialMetricEntry]:
        """Fetch HK-stock financials via the akshare subprocess (eastmoney HK API).

        Runs in the isolated akshare_mcp venv — importing akshare into the
        backend process is not possible (not a declared dependency).
        """
        import asyncio as _asyncio
        import json as _json

        from market.akshare_executor import build_akshare_env, run_akshare

        try:
            stdout = await _asyncio.to_thread(
                run_akshare, _HK_FINANCIALS_CODE, build_akshare_env(ticker)
            )
        except Exception:
            return []
        if not stdout:
            return []

        name_to_en = dict(HK_METRICS)
        results: list[FinancialMetricEntry] = []
        for line in stdout.splitlines():
            if not line.startswith("__R__:"):
                continue
            try:
                rows = _json.loads(line[6:])
            except _json.JSONDecodeError:
                return []
            for r in rows:
                en_name = name_to_en.get(r.get("cn"))
                if en_name is None:
                    continue
                results.append(
                    FinancialMetricEntry(
                        fiscal_year=int(r["year"]),
                        fiscal_period="Annual",
                        metric_name=en_name,
                        metric_value=float(r["value"]),
                    )
                )
            break
        return results
