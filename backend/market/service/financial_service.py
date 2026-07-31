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
                results.append(FinancialMetricEntry(
                    fiscal_year=row.fiscal_year,
                    fiscal_period=row.fiscal_period,
                    metric_name=m_name,
                    metric_value=m_value,
                ))
        return results

    async def upsert_financials(
        self, ticker: str, metrics: list[FinancialMetricEntry]
    ) -> int:
        """Bulk upsert financial metrics into PostgreSQL."""
        count = await self.repo.upsert(ticker, metrics)

        if count:
            await self.events.record(
                source="market", event_type="financials.ingested",
                entity_type="financial_metric", entity_id=ticker,
                payload={"count": count, "ticker": ticker},
            )

        # Record freshness
        from market.service.freshness_service import FreshnessService
        freshness = FreshnessService(self.session)
        await freshness.record_fetch(ticker, "financials", record_count=count, status="ok")

        return count

    async def _fetch_akshare_financials(self, ticker: str) -> list[FinancialMetricEntry]:
        """Fetch HK-stock financial data via akshare (eastmoney HK API)."""
        import akshare as ak
        import asyncio as _asyncio

        hk_symbol = ticker.zfill(5)

        def _fetch():
            df = ak.stock_financial_hk_report_em(
                stock=hk_symbol, symbol="利润表", indicator="年度"
            )
            results: list[FinancialMetricEntry] = []
            for cn_name, en_name in HK_METRICS:
                subset = df[df["STD_ITEM_NAME"] == cn_name]
                for _, row in subset.iterrows():
                    report_date = row["REPORT_DATE"]
                    if isinstance(report_date, str):
                        year = int(report_date[:4])
                    else:
                        year = report_date.year
                    value = float(row["AMOUNT"])
                    results.append(FinancialMetricEntry(
                        fiscal_year=year,
                        fiscal_period="Annual",
                        metric_name=en_name,
                        metric_value=value,
                    ))
            return results

        return await _asyncio.to_thread(_fetch)
