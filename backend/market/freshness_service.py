"""Data freshness service — tracks when each ticker's data was last fetched.

Used by PriceService, FinancialService, ProfileService to record fetch timestamps,
and by the dashboard/freshness API to report data staleness.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from market.models import DataFreshness


# How old is "stale" for each data type (in hours)
STALE_THRESHOLD_HOURS: dict[str, int] = {
    "prices": 24,       # daily price — stale after 1 day
    "financials": 168,  # 7 days
    "profile": 168,     # 7 days (company profile rarely changes)
    "news": 6,          # 6 hours
}


class FreshnessService:
    """Record and query data freshness for each ticker."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_fetch(
        self,
        ticker: str,
        data_type: str,
        record_count: int | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> DataFreshness:
        """Upsert freshness record after a successful (or failed) fetch."""
        stmt = select(DataFreshness).where(
            DataFreshness.ticker == ticker.upper(),
            DataFreshness.data_type == data_type,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.checked_at = datetime.now(timezone.utc)
            existing.status = status
            existing.record_count = record_count
            existing.error_message = error_message
        else:
            existing = DataFreshness(
                ticker=ticker.upper(),
                data_type=data_type,
                checked_at=datetime.now(timezone.utc),
                record_count=record_count,
                status=status,
                error_message=error_message,
            )
            self.session.add(existing)

        await self.session.flush()
        return existing

    async def get_freshness(
        self,
        ticker: str | None = None,
        data_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query freshness records, optionally filtered."""
        stmt = select(DataFreshness).order_by(DataFreshness.checked_at.desc())

        if ticker:
            stmt = stmt.where(DataFreshness.ticker == ticker.upper())
        if data_type:
            stmt = stmt.where(DataFreshness.data_type == data_type)
        if status:
            stmt = stmt.where(DataFreshness.status == status)

        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        entries = list(result.scalars().all())

        now = datetime.now(timezone.utc)
        output = []
        for e in entries:
            threshold_hours = STALE_THRESHOLD_HOURS.get(e.data_type, 24)
            age_hours = (now - e.checked_at).total_seconds() / 3600
            is_stale = age_hours > threshold_hours
            output.append({
                "ticker": e.ticker,
                "data_type": e.data_type,
                "checked_at": e.checked_at.isoformat(),
                "age_hours": round(age_hours, 1),
                "is_stale": is_stale,
                "stale_threshold_hours": threshold_hours,
                "record_count": e.record_count,
                "status": e.status,
                "error_message": e.error_message,
            })
        return output

    async def get_ticker_summary(self, ticker: str) -> dict[str, Any]:
        """Get freshness summary for a single ticker across all data types."""
        records = await self.get_freshness(ticker=ticker)
        summary: dict[str, Any] = {"ticker": ticker.upper(), "data_types": {}}
        for r in records:
            summary["data_types"][r["data_type"]] = r
        summary["all_fresh"] = all(
            not dt["is_stale"] for dt in summary["data_types"].values()
        )
        return summary

    async def get_stale_tickers(
        self,
        data_type: str | None = None,
        min_age_hours: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all tickers with stale data."""
        all_records = await self.get_freshness(data_type=data_type)
        stale = []
        for r in all_records:
            threshold = min_age_hours or STALE_THRESHOLD_HOURS.get(r["data_type"], 24)
            if r["age_hours"] > threshold:
                stale.append(r)
        return stale

    async def get_overall_stats(self) -> dict[str, Any]:
        """Aggregate freshness stats across all tickers."""
        result = await self.session.execute(
            select(
                DataFreshness.data_type,
                func.count(DataFreshness.id).label("count"),
                func.max(DataFreshness.checked_at).label("newest"),
                func.min(DataFreshness.checked_at).label("oldest"),
            ).group_by(DataFreshness.data_type)
        )
        rows = result.all()
        stats = {}
        now = datetime.now(timezone.utc)
        for row in rows:
            max_age = (now - row.newest).total_seconds() / 3600 if row.newest else None
            min_age = (now - row.oldest).total_seconds() / 3600 if row.oldest else None
            stats[row.data_type] = {
                "count": row.count,
                "newest_checked_at": row.newest.isoformat() if row.newest else None,
                "newest_age_hours": round(max_age, 1) if max_age else None,
                "oldest_age_hours": round(min_age, 1) if min_age else None,
            }
        return stats
