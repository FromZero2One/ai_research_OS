"""Data freshness service — tracks when each ticker's data was last fetched.

Used by PriceService, FinancialService, ProfileService to record fetch timestamps,
and by the dashboard/freshness API to report data staleness.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from market.repositories import FreshnessRepository

# How old is "stale" for each data type (in hours)
STALE_THRESHOLD_HOURS: dict[str, int] = {
    "prices": 24,  # daily price — stale after 1 day
    "financials": 168,  # 7 days
    "profile": 168,  # 7 days (company profile rarely changes)
    "news": 6,  # 6 hours
}


class FreshnessService:
    """Record and query data freshness for each ticker."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = FreshnessRepository(session)

    async def record_fetch(
        self,
        ticker: str,
        data_type: str,
        record_count: int | None = None,
        status: str = "ok",
        error_message: str | None = None,
    ) -> Any:
        """Upsert freshness record after a successful (or failed) fetch."""
        return await self.repo.upsert(
            ticker,
            data_type,
            record_count=record_count,
            status=status,
            error_message=error_message,
        )

    async def get_freshness(
        self,
        ticker: str | None = None,
        data_type: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query freshness records, optionally filtered."""
        entries = await self.repo.list_all(
            ticker=ticker,
            data_type=data_type,
            status=status,
            limit=limit,
        )

        now = datetime.now(UTC)
        output = []
        for e in entries:
            threshold_hours = STALE_THRESHOLD_HOURS.get(e.data_type, 24)
            age_hours = (now - e.checked_at).total_seconds() / 3600
            is_stale = age_hours > threshold_hours
            # 两级预警：>80% 阈值 warn，超过阈值 stale
            health = "ok"
            if is_stale:
                health = "stale"
            elif age_hours > threshold_hours * 0.8:
                health = "warn"
            output.append(
                {
                    "ticker": e.ticker,
                    "data_type": e.data_type,
                    "checked_at": e.checked_at.isoformat(),
                    "age_hours": round(age_hours, 1),
                    "is_stale": is_stale,
                    "health": health,
                    "stale_threshold_hours": threshold_hours,
                    "record_count": e.record_count,
                    "status": e.status,
                    "error_message": e.error_message,
                }
            )
        return output

    async def get_ticker_summary(self, ticker: str) -> dict[str, Any]:
        """Get freshness summary for a single ticker across all data types."""
        records = await self.get_freshness(ticker=ticker)
        summary: dict[str, Any] = {"ticker": ticker.upper(), "data_types": {}}
        for r in records:
            summary["data_types"][r["data_type"]] = r
        summary["all_fresh"] = all(not dt["is_stale"] for dt in summary["data_types"].values())
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
        rows = await self.repo.stats()
        stats = {}
        now = datetime.now(UTC)
        for data_type, count, newest, oldest in rows:
            max_age = (now - newest).total_seconds() / 3600 if newest else None
            min_age = (now - oldest).total_seconds() / 3600 if oldest else None
            stats[data_type] = {
                "count": count,
                "newest_checked_at": newest.isoformat() if newest else None,
                "newest_age_hours": round(max_age, 1) if max_age else None,
                "oldest_age_hours": round(min_age, 1) if min_age else None,
            }
        return stats

    async def get_quality_dashboard(self) -> dict[str, Any]:
        """数据质量看板：总览 + 各级预警清单 + 单一数据源依赖检测。

        source_concentration 指标用于发现某数据类型只覆盖极少 ticker 的
        单一来源依赖风险。
        """
        all_records = await self.get_freshness(limit=1000)
        stats = await self.get_overall_stats()

        stale: list[dict[str, Any]] = []
        warn: list[dict[str, Any]] = []
        for r in all_records:
            if r["health"] == "stale":
                stale.append(r)
            elif r["health"] == "warn":
                warn.append(r)

        # 单一数据源依赖：某数据类型覆盖的 ticker 数占总 ticker 数比例过低即预警
        tickers = {r["ticker"] for r in all_records}
        coverage: dict[str, int] = {}
        for r in all_records:
            coverage[r["data_type"]] = coverage.get(r["data_type"], 0) + 1
        total = len(tickers) or 1
        concentration = {
            dt: round(c / total, 2) for dt, c in coverage.items()
        }

        return {
            "overall_stats": stats,
            "counts": {
                "total_records": len(all_records),
                "total_tickers": len(tickers),
                "stale": len(stale),
                "warn": len(warn),
            },
            "stale_list": stale[:50],
            "warn_list": warn[:50],
            "source_coverage_ratio": concentration,
        }
