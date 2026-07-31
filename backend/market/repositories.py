"""Market Center repositories — persistence layer over ORM models.

Concrete repositories map ORM models to/from the domain DTOs defined in
``market.domain``. Services talk to repositories, never to models directly.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import desc, func, select

from core.crud import DomainRepository
from market.domain import FinancialMetricEntry, FreshnessEntry, PriceEntry
from market.models import DataFreshness, FinancialMetric, StockPrice


class PriceRepository(DomainRepository[StockPrice]):
    """Persistence for stock price data."""

    model = StockPrice

    def to_dto(self, obj: StockPrice) -> PriceEntry:
        return PriceEntry.from_model(obj)

    async def get_for_ticker(
        self,
        ticker: str,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[PriceEntry]:
        stmt = select(StockPrice).where(StockPrice.ticker == ticker.upper())
        if start_date:
            stmt = stmt.where(StockPrice.date >= start_date)
        if end_date:
            stmt = stmt.where(StockPrice.date <= end_date)
        stmt = stmt.order_by(desc(StockPrice.date)).limit(limit)
        result = await self.session.execute(stmt)
        return [PriceEntry.from_model(row) for row in result.scalars().all()]

    async def upsert(self, ticker: str, entries: list[PriceEntry]) -> int:
        """Insert rows that don't already exist; returns inserted count."""
        count = 0
        for entry in entries:
            existing = await self.session.execute(
                select(StockPrice).where(
                    StockPrice.ticker == ticker.upper(),
                    StockPrice.date == entry.date,
                )
            )
            if existing.scalar_one_or_none():
                continue
            self.session.add(entry.to_model(StockPrice, ticker))
            count += 1
        if count:
            await self.session.flush()
        return count

    async def delete_for_ticker(self, ticker: str) -> int:
        result = await self.session.execute(
            sa_delete(StockPrice).where(StockPrice.ticker == ticker.upper())
        )
        return result.rowcount or 0


class FinancialRepository(DomainRepository[FinancialMetric]):
    """Persistence for financial metrics."""

    model = FinancialMetric

    def to_dto(self, obj: FinancialMetric) -> FinancialMetricEntry:
        return FinancialMetricEntry.from_model(obj)

    async def get_for_ticker(
        self,
        ticker: str,
        metric: str | None = None,
        fiscal_year: int | None = None,
        limit: int = 500,
    ) -> list[FinancialMetricEntry]:
        stmt = select(FinancialMetric).where(FinancialMetric.ticker == ticker)
        if metric:
            stmt = stmt.where(FinancialMetric.metric_name == metric)
        if fiscal_year:
            stmt = stmt.where(FinancialMetric.fiscal_year == fiscal_year)
        stmt = stmt.order_by(
            FinancialMetric.fiscal_year.desc(), FinancialMetric.fiscal_period,
        ).limit(limit)
        result = await self.session.execute(stmt)
        return [FinancialMetricEntry.from_model(m) for m in result.scalars().all()]

    async def upsert(self, ticker: str, entries: list[FinancialMetricEntry]) -> int:
        """Insert financial metrics that don't already exist; returns inserted count."""
        count = 0
        for entry in entries:
            existing = await self.session.execute(
                select(FinancialMetric).where(
                    FinancialMetric.ticker == ticker.upper(),
                    FinancialMetric.fiscal_year == entry.fiscal_year,
                    FinancialMetric.fiscal_period == entry.fiscal_period,
                    FinancialMetric.metric_name == entry.metric_name,
                )
            )
            if existing.scalar_one_or_none():
                continue
            self.session.add(entry.to_model(FinancialMetric, ticker))
            count += 1
        if count:
            await self.session.flush()
        return count


class FreshnessRepository(DomainRepository[DataFreshness]):
    """Persistence for data freshness records."""

    model = DataFreshness

    def to_dto(self, obj: DataFreshness) -> FreshnessEntry:
        return FreshnessEntry.from_model(obj)

    async def get_for_ticker_type(
        self, ticker: str, data_type: str
    ) -> DataFreshness | None:
        stmt = select(DataFreshness).where(
            DataFreshness.ticker == ticker.upper(),
            DataFreshness.data_type == data_type,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        ticker: str,
        data_type: str,
        record_count: int | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> DataFreshness:
        """Insert or update a freshness record; returns the ORM object."""
        now = datetime.now(timezone.utc)
        existing = await self.get_for_ticker_type(ticker, data_type)
        if existing:
            existing.checked_at = now
            existing.status = status
            existing.record_count = record_count
            existing.error_message = error_message
        else:
            existing = DataFreshness(
                ticker=ticker.upper(),
                data_type=data_type,
                checked_at=now,
                record_count=record_count,
                status=status,
                error_message=error_message,
            )
            self.session.add(existing)
        await self.session.flush()
        return existing

    async def list_all(
        self,
        ticker: str | None = None,
        data_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[DataFreshness]:
        stmt = select(DataFreshness).order_by(DataFreshness.checked_at.desc())
        if ticker:
            stmt = stmt.where(DataFreshness.ticker == ticker.upper())
        if data_type:
            stmt = stmt.where(DataFreshness.data_type == data_type)
        if status:
            stmt = stmt.where(DataFreshness.status == status)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def stats(self) -> list[tuple[str, int, datetime | None, datetime | None]]:
        """Aggregate stats grouped by data_type: (type, count, newest, oldest)."""
        result = await self.session.execute(
            select(
                DataFreshness.data_type,
                func.count(DataFreshness.id).label("count"),
                func.max(DataFreshness.checked_at).label("newest"),
                func.min(DataFreshness.checked_at).label("oldest"),
            ).group_by(DataFreshness.data_type)
        )
        return [
            (row.data_type, row.count, row.newest, row.oldest)
            for row in result.all()
        ]
