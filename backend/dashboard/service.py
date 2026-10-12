"""Dashboard service — aggregates data from all modules for the daily workspace.

All methods use batch queries (not N+1) to avoid per-item round-trips.
Shared watchlist/research/price queries live in core.shared_queries.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.shared_queries import (
    latest_price_by_ticker,
    latest_research_by_company,
    load_watched_companies,
)


def _days_since(dt) -> int | None:
    """距某时刻的天数（UTC）。"""
    if dt is None:
        return None
    return (datetime.now(UTC) - dt).days


def _research_status(days_since: int | None) -> str:
    """按研究间隔给出关注状态。"""
    if days_since is not None and days_since > 30:
        return "need_research"
    if days_since is not None and days_since > 14:
        return "attention"
    return "normal"


class DashboardService:
    """Dashboard data aggregation — read-only, no new entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Morning Brief ─────────────────────────────────────────────

    async def get_latest_brief(self) -> dict[str, Any] | None:
        """Fetch the most recent morning brief from MorningBrief table."""
        from core.morning_brief import MorningBrief

        result = await self.session.execute(
            select(MorningBrief).order_by(desc(MorningBrief.generated_at)).limit(1)
        )
        brief = result.scalar_one_or_none()
        if not brief:
            return None
        return {
            "content": brief.content,
            "generated_at": brief.generated_at.isoformat() if brief.generated_at else None,
        }

    # ── Watchlist Summary (batch-queried) ─────────────────────────

    async def get_watchlist_summary(self) -> list[dict[str, Any]]:
        """Watched companies (is_active) enriched with prices + research.

        The watchlist merged into Company — watched == is_active. Response keeps
        the old shape (a single "自选" group) so the frontend is unchanged.
        """
        companies = await load_watched_companies(self.session)
        if not companies:
            return []

        all_tickers = [c.ticker for c in companies]
        company_ids = [c.id for c in companies]

        # Batch: latest price per ticker + latest research per company
        latest_price_map = await latest_price_by_ticker(self.session, all_tickers)
        research_by_company = await latest_research_by_company(self.session, company_ids)

        # Assemble (no per-item queries)
        items_data = []
        for company in companies:
            price = latest_price_map.get(company.ticker)
            research = research_by_company.get(company.id)
            days_since_research = _days_since(research.created_at if research else None)

            items_data.append(
                {
                    "id": str(company.id),
                    "ticker": company.ticker,
                    "company_name": company.name,
                    "sector": company.sector,
                    "priority": company.priority,
                    "target_price": company.target_price,
                    "reason": company.reason,
                    "latest_price": price.close if price else None,
                    "price_date": price.date.isoformat() if price and price.date else None,
                    "price_change": (
                        round(((price.close - price.open) / price.open) * 100, 2)
                        if (price and price.open is not None and price.close is not None)
                        else None
                    ),
                    "status": _research_status(days_since_research),
                    "thesis": research.thesis if research else None,
                    "last_research_at": (
                        research.created_at.isoformat()
                        if research and research.created_at
                        else None
                    ),
                    "days_since_research": days_since_research,
                }
            )

        items_data.sort(key=lambda x: (x["priority"], x["ticker"]))
        summaries = [
            {
                "watchlist_id": "watched",
                "watchlist_name": "自选",
                "items": items_data,
            }
        ]

        return summaries

    # ── Research Reminders (batch-queried) ────────────────────────

    async def get_research_reminders(self) -> list[dict[str, Any]]:
        """Find items needing research attention (30d+ since last research).

        Before: O(1 + N*2) — one company + one research query per item.
        After:  O(1 + 2) — batch companies, then batch research.
        """
        companies = await load_watched_companies(self.session)
        if not companies:
            return []

        research_by_company = await latest_research_by_company(
            self.session, [c.id for c in companies]
        )

        reminders: list[dict[str, Any]] = []
        for company in companies:
            research = research_by_company.get(company.id)
            days_since = _days_since(research.created_at if research else None)

            reasons = []
            if days_since and days_since > 30:
                reasons.append(f"距离上次研究 {days_since} 天")

            if reasons:
                reminders.append(
                    {
                        "ticker": company.ticker,
                        "company_name": company.name,
                        "days_since_research": days_since,
                        "reasons": reasons,
                        "priority": company.priority,
                    }
                )

        reminders.sort(key=lambda x: -(int(x["days_since_research"] or 0)))
        return reminders

    # ── Market Overview (batch-queried) ───────────────────────────

    async def get_market_overview(self) -> list[dict[str, Any]]:
        """Recent price movements across tracked companies.

        Single query: load last 90 days of prices for all tracked companies,
        then take the latest 2 per ticker in Python.
        """
        companies = await load_watched_companies(self.session)
        if not companies:
            return []

        tickers = [c.ticker for c in companies]

        # Single batch query: all prices from last 90 days
        from market.models import StockPrice

        price_rows = await self.session.execute(
            select(StockPrice)
            .where(
                StockPrice.ticker.in_(tickers),
                StockPrice.date >= func.current_date() - text("interval '90 days'"),
            )
            .order_by(StockPrice.ticker, StockPrice.date.desc())
        )
        all_prices = list(price_rows.scalars().all())

        # Take latest 2 per ticker in Python
        latest_by_ticker: dict[str, StockPrice] = {}
        prev_by_ticker: dict[str, StockPrice] = {}
        for p in all_prices:
            if p.ticker not in latest_by_ticker:
                latest_by_ticker[p.ticker] = p
            elif p.ticker not in prev_by_ticker:
                prev_by_ticker[p.ticker] = p

        overview: list[dict[str, Any]] = []
        for c in companies:
            latest = latest_by_ticker.get(c.ticker)
            prev = prev_by_ticker.get(c.ticker)
            if not latest or not prev:
                continue

            change_pct = (
                round(((latest.close - prev.close) / prev.close) * 100, 2)
                if prev.close is not None and latest.close is not None
                else None
            )

            overview.append(
                {
                    "ticker": c.ticker,
                    "company_name": c.name,
                    "sector": c.sector,
                    "latest_price": latest.close,
                    "price_date": latest.date.isoformat() if latest.date else None,
                    "change_pct": change_pct,
                }
            )

        overview.sort(key=lambda x: abs(x["change_pct"] or 0), reverse=True)
        return overview[:10]

    # ── Full Dashboard ────────────────────────────────────────────

    async def get_dashboard(self) -> dict[str, Any]:
        """Aggregate everything for the daily workspace homepage — all batch."""
        from research.models import ResearchSession

        brief = await self.get_latest_brief()
        watchlist = await self.get_watchlist_summary()
        reminders = await self.get_research_reminders()

        result = await self.session.execute(
            select(ResearchSession).order_by(desc(ResearchSession.created_at)).limit(5)
        )
        recent = result.scalars().all()

        return {
            "morning_brief": brief,
            "watchlist": watchlist,
            "research_reminders": reminders,
            "recent_research": [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "question": s.question,
                    "status": s.status,
                    "thesis": s.thesis,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                }
                for s in recent
            ],
        }
