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

    async def get_coverage_matrix(self) -> dict[str, Any]:
        """数据覆盖矩阵：关注公司 × 数据类型。

        与 quality_dashboard 的区别：quality_dashboard 只统计已有记录，
        本方法对"该有而没有"的缺口显式标 missing——关注公司从未抓过
        财务数据这类问题只有矩阵视角能暴露。
        """
        from sqlalchemy import select as sa_select

        from company.models import Company
        from document.models import Document, DocumentChunk

        result = await self.session.execute(
            sa_select(Company).where(Company.is_active.is_(True)).order_by(Company.ticker)
        )
        companies = result.scalars().all()

        # 定性覆盖：已索引文档 + 含 mda/risk 切片 → ok；仅已索引 → partial；无 → missing
        indexed_ids = {
            row[0]
            for row in (
                await self.session.execute(
                    sa_select(Document.company_id)
                    .where(Document.is_indexed.is_(True), Document.company_id.isnot(None))
                    .distinct()
                )
            ).all()
        }
        mda_risk_ids = {
            row[0]
            for row in (
                await self.session.execute(
                    sa_select(Document.company_id)
                    .join(DocumentChunk, DocumentChunk.document_id == Document.id)
                    .where(
                        Document.is_indexed.is_(True),
                        Document.company_id.isnot(None),
                        DocumentChunk.content_type.in_(["mda", "risk"]),
                    )
                    .distinct()
                )
            ).all()
        }

        def _qual_health(cid) -> str:
            if cid in mda_risk_ids:
                return "ok"
            if cid in indexed_ids:
                return "partial"
            return "missing"

        records = await self.get_freshness(limit=5000)
        by_ticker: dict[str, dict[str, dict[str, Any]]] = {}
        for r in records:
            by_ticker.setdefault(r["ticker"], {})[r["data_type"]] = r

        tracked_types = list(STALE_THRESHOLD_HOURS.keys())
        rows: list[dict[str, Any]] = []
        for c in companies:
            types = by_ticker.get(c.ticker.upper(), {})
            cells: dict[str, Any] = {}
            missing: list[str] = []
            for dt in tracked_types:
                rec = types.get(dt)
                if rec is None:
                    cells[dt] = {"health": "missing"}
                    missing.append(dt)
                else:
                    cells[dt] = {
                        "health": rec["health"],
                        "age_hours": rec["age_hours"],
                        "checked_at": rec["checked_at"],
                        "record_count": rec["record_count"],
                    }
            qual = _qual_health(c.id)
            qual_rank = {"ok": dt_priority("ok"), "partial": dt_priority("warn"), "missing": dt_priority("missing")}[qual]

            worst = "ok"
            for cell in cells.values():
                h = cell["health"]
                if h == "stale" or (h == "missing" and dt_priority(h) > dt_priority(worst)):
                    worst = h
                elif h == "warn" and worst == "ok":
                    worst = "warn"
                elif h == "missing" and worst not in ("stale", "missing"):
                    worst = "missing" if worst == "missing" else worst
            if qual_rank > dt_priority(worst):
                worst = "warn" if qual == "partial" else "missing"
            rows.append(
                {
                    "ticker": c.ticker,
                    "name": c.name,
                    "cells": cells,
                    "missing": missing,
                    "qualitative": {"health": qual, "has_mda_risk": qual == "ok"},
                    "worst_health": worst,
                }
            )

        stale_count = sum(1 for r in rows if r["worst_health"] == "stale")
        missing_count = sum(1 for r in rows if r["missing"])
        return {
            "data_types": tracked_types,
            "rows": rows,
            "counts": {
                "companies": len(rows),
                "fully_covered": sum(
                    1 for r in rows if not r["missing"] and r["worst_health"] == "ok"
                ),
                "with_gaps": missing_count,
                "stale": stale_count,
                "qualitative_ok": sum(1 for r in rows if r["qualitative"]["health"] == "ok"),
            },
        }


def dt_priority(health: str) -> int:
    """健康度严重程度排序（missing 视为最严重——数据缺口）。"""
    return {"missing": 3, "stale": 2, "warn": 1, "ok": 0}.get(health, 0)
