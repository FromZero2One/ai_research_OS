"""Financial metrics service — query and ingest financial data.

A-stocks → Akshare MySQL (stock_yjbb_em)
HK stocks → akshare eastmoney HK API
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter
from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import is_a_stock
from market.models import FinancialMetric

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
    ) -> list[FinancialMetric]:
        """Get financial metrics — PG first, MySQL for A-stocks, akshare for HK."""
        ticker_upper = ticker.upper()

        pg_metrics = await self._get_financials_from_pg(ticker_upper, metric, fiscal_year)
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
                return await self._get_financials_from_pg(ticker_upper, metric, fiscal_year)
        except Exception:
            logger.warning("Failed to fetch financials from akshare HK for %s", ticker)
            pass

        return []

    async def _get_financials_from_pg(
        self, ticker: str, metric: str | None, fiscal_year: int | None
    ) -> list[FinancialMetric]:
        stmt = select(FinancialMetric).where(FinancialMetric.ticker == ticker)
        if metric:
            stmt = stmt.where(FinancialMetric.metric_name == metric)
        if fiscal_year:
            stmt = stmt.where(FinancialMetric.fiscal_year == fiscal_year)
        stmt = stmt.order_by(
            FinancialMetric.fiscal_year.desc(), FinancialMetric.fiscal_period,
        ).limit(500)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

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

    async def upsert_financials(self, ticker: str, metrics: list[FinancialMetric]) -> int:
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
                source="market", event_type="financials.ingested",
                entity_type="financial_metric", entity_id=ticker,
                payload={"count": count, "ticker": ticker},
            )

        # Record freshness
        from market.freshness_service import FreshnessService
        freshness = FreshnessService(self.session)
        await freshness.record_fetch(ticker, "financials", record_count=count, status="ok")

        return count

    async def _fetch_akshare_financials(self, ticker: str) -> list[FinancialMetric]:
        """Fetch HK-stock financial data via akshare (eastmoney HK API)."""
        import akshare as ak
        import asyncio as _asyncio

        hk_symbol = ticker.zfill(5)

        def _fetch():
            df = ak.stock_financial_hk_report_em(
                stock=hk_symbol, symbol="利润表", indicator="年度"
            )
            results: list[FinancialMetric] = []
            for cn_name, en_name in HK_METRICS:
                subset = df[df["STD_ITEM_NAME"] == cn_name]
                for _, row in subset.iterrows():
                    report_date = row["REPORT_DATE"]
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
