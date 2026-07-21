"""Dashboard service — aggregates data from all modules for the daily workspace."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.event_log import EventLog


class DashboardService:
    """Dashboard data aggregation — read-only, no new entities."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Morning Brief ─────────────────────────────────────────────

    async def get_latest_brief(self) -> dict[str, Any] | None:
        """Fetch the most recent morning brief from EventLog."""
        result = await self.session.execute(
            select(EventLog)
            .where(
                EventLog.source == "scheduler",
                EventLog.event_type == "morning_brief.generated",
            )
            .order_by(desc(EventLog.occurred_at))
            .limit(1)
        )
        entry = result.scalar_one_or_none()
        if not entry or not entry.payload:
            return None
        return {
            "content": entry.payload.get("content", ""),
            "generated_at": entry.occurred_at.isoformat() if entry.occurred_at else None,
        }

    # ── Watchlist Summary ─────────────────────────────────────────

    async def get_watchlist_summary(self) -> list[dict[str, Any]]:
        """Fetch all watchlists with items enriched with company info + prices + research."""
        from company.models import Company
        from market.models import StockPrice
        from portfolio.models import Watchlist
        from research.models import ResearchSession

        result = await self.session.execute(
            select(Watchlist).options(selectinload(Watchlist.items))
        )
        watchlists = list(result.scalars().all())

        summaries = []
        for wl in watchlists:
            items_data = []
            for item in wl.items:
                ticker = item.ticker

                # Company info
                company_result = await self.session.execute(
                    select(Company).where(Company.ticker == ticker).limit(1)
                )
                company = company_result.scalar_one_or_none()

                # Latest price
                price_result = await self.session.execute(
                    select(StockPrice)
                    .where(StockPrice.ticker == ticker)
                    .order_by(desc(StockPrice.date))
                    .limit(1)
                )
                latest_price = price_result.scalar_one_or_none()

                # Latest research for this company/ticker
                if company:
                    research_result = await self.session.execute(
                        select(ResearchSession)
                        .where(ResearchSession.company_id == company.id)
                        .order_by(desc(ResearchSession.created_at))
                        .limit(1)
                    )
                    latest_research = research_result.scalar_one_or_none()
                else:
                    latest_research = None

                # Compute status
                days_since_research = None
                status = "normal"
                if latest_research and latest_research.created_at:
                    delta = datetime.now(timezone.utc) - latest_research.created_at
                    days_since_research = delta.days
                    if days_since_research and days_since_research > 30:
                        status = "need_research"
                    elif days_since_research and days_since_research > 14:
                        status = "attention"

                items_data.append({
                    "id": str(item.id),
                    "ticker": ticker,
                    "company_name": company.name if company else ticker,
                    "sector": company.sector if company else None,
                    "priority": item.priority,
                    "target_price": item.target_price,
                    "reason": item.reason,
                    "latest_price": latest_price.close if latest_price else None,
                    "price_date": latest_price.date.isoformat() if latest_price and latest_price.date else None,
                    "price_change": (
                        round(((latest_price.close - latest_price.open) / latest_price.open) * 100, 2)
                        if latest_price and latest_price.open
                        else None
                    ),
                    "status": status,
                    "thesis": latest_research.thesis if latest_research else None,
                    "last_research_at": latest_research.created_at.isoformat() if latest_research and latest_research.created_at else None,
                    "days_since_research": days_since_research,
                })

            # Sort by priority (lower = higher priority)
            items_data.sort(key=lambda x: (x["priority"], x["ticker"]))

            summaries.append({
                "watchlist_id": str(wl.id),
                "watchlist_name": wl.name,
                "items": items_data,
            })

        return summaries

    # ── Research Reminders ────────────────────────────────────────

    async def get_research_reminders(self) -> list[dict[str, Any]]:
        """Find items needing research attention (30d+ since last research)."""
        from company.models import Company
        from portfolio.models import WatchlistItem
        from research.models import ResearchSession

        result = await self.session.execute(
            select(WatchlistItem)
        )
        items = list(result.scalars().all())

        reminders = []
        for item in items:
            company_result = await self.session.execute(
                select(Company).where(Company.ticker == item.ticker).limit(1)
            )
            company = company_result.scalar_one_or_none()
            if not company:
                continue

            research_result = await self.session.execute(
                select(ResearchSession)
                .where(ResearchSession.company_id == company.id)
                .order_by(desc(ResearchSession.created_at))
                .limit(1)
            )
            latest = research_result.scalar_one_or_none()

            days_since = None
            if latest and latest.created_at:
                delta = datetime.now(timezone.utc) - latest.created_at
                days_since = delta.days

            reasons = []
            if days_since and days_since > 30:
                reasons.append(f"距离上次研究 {days_since} 天")

            if reasons:
                reminders.append({
                    "ticker": item.ticker,
                    "company_name": company.name,
                    "days_since_research": days_since,
                    "reasons": reasons,
                    "priority": item.priority,
                })

        reminders.sort(key=lambda x: -(x["days_since_research"] or 0))
        return reminders

    # ── Full Dashboard ────────────────────────────────────────────

    async def get_dashboard(self) -> dict[str, Any]:
        """Aggregate everything for the daily workspace homepage."""
        from research.models import ResearchSession

        brief = await self.get_latest_brief()
        watchlist = await self.get_watchlist_summary()
        reminders = await self.get_research_reminders()

        # Recent research sessions
        result = await self.session.execute(
            select(ResearchSession)
            .order_by(desc(ResearchSession.created_at))
            .limit(5)
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
