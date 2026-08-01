"""Dashboard service — aggregates data from all modules for the daily workspace.

All methods use batch queries (not N+1) to avoid per-item round-trips.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


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
        """Fetch all watchlists with items enriched with company info + prices + research.

        Before: O(1 + N*3) queries — one per item.
        After:  O(1 + 3) queries — batch all companies, prices, and research.
        """
        from company.models import Company
        from market.models import StockPrice
        from portfolio.models import Watchlist
        from research.models import ResearchSession

        # 1. Load watchlists with items
        result = await self.session.execute(
            select(Watchlist).options(selectinload(Watchlist.items))
        )
        watchlists = list(result.scalars().all())

        # Collect all tickers and company_ids in one pass
        all_tickers: list[str] = []
        for wl in watchlists:
            for item in wl.items:
                all_tickers.append(item.ticker)

        if not all_tickers:
            return []

        # 2. Batch-load companies by ticker → {ticker: Company}
        comp_result = await self.session.execute(
            select(Company).where(Company.ticker.in_(all_tickers))
        )
        company_by_ticker: dict[str, Company] = {c.ticker: c for c in comp_result.scalars().all()}
        company_ids = [c.id for c in company_by_ticker.values()]

        # 3. Batch-load latest price per ticker (GROUP BY → max date)
        subq = (
            select(StockPrice.ticker, func.max(StockPrice.date).label("max_date"))
            .where(StockPrice.ticker.in_(all_tickers))
            .group_by(StockPrice.ticker)
            .subquery()
        )
        latest_px = await self.session.execute(
            select(StockPrice).join(
                subq,
                (StockPrice.ticker == subq.c.ticker) & (StockPrice.date == subq.c.max_date),
            )
        )
        latest_price_by_ticker: dict[str, StockPrice] = {
            p.ticker: p for p in latest_px.scalars().all()
        }

        # 4. Batch-load latest research per company (GROUP BY → max created_at)
        research_by_company: dict[str, ResearchSession] = {}
        if company_ids:
            subq_rs = (
                select(
                    ResearchSession.company_id,
                    func.max(ResearchSession.created_at).label("max_created"),
                )
                .where(ResearchSession.company_id.in_(company_ids))
                .group_by(ResearchSession.company_id)
                .subquery()
            )
            rs_result = await self.session.execute(
                select(ResearchSession).join(
                    subq_rs,
                    (ResearchSession.company_id == subq_rs.c.company_id)
                    & (ResearchSession.created_at == subq_rs.c.max_created),
                )
            )
            for rs in rs_result.scalars().all():
                research_by_company[str(rs.company_id)] = rs

        # 5. Assemble (no per-item queries)
        summaries = []
        for wl in watchlists:
            items_data = []
            for item in wl.items:
                company = company_by_ticker.get(item.ticker)
                price = latest_price_by_ticker.get(item.ticker)
                research = research_by_company.get(str(company.id)) if company else None

                days_since_research = None
                status = "normal"
                if research and research.created_at:
                    delta = datetime.now(UTC) - research.created_at
                    days_since_research = delta.days
                    if days_since_research and days_since_research > 30:
                        status = "need_research"
                    elif days_since_research and days_since_research > 14:
                        status = "attention"

                items_data.append(
                    {
                        "id": str(item.id),
                        "ticker": item.ticker,
                        "company_name": company.name if company else item.ticker,
                        "sector": company.sector if company else None,
                        "priority": item.priority,
                        "target_price": item.target_price,
                        "reason": item.reason,
                        "latest_price": price.close if price else None,
                        "price_date": price.date.isoformat() if price and price.date else None,
                        "price_change": (
                            round(((price.close - price.open) / price.open) * 100, 2)
                            if (price and price.open is not None and price.close is not None)
                            else None
                        ),
                        "status": status,
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
            summaries.append(
                {
                    "watchlist_id": str(wl.id),
                    "watchlist_name": wl.name,
                    "items": items_data,
                }
            )

        return summaries

    # ── Research Reminders (batch-queried) ────────────────────────

    async def get_research_reminders(self) -> list[dict[str, Any]]:
        """Find items needing research attention (30d+ since last research).

        Before: O(1 + N*2) — one company + one research query per item.
        After:  O(1 + 2) — batch companies, then batch research.
        """
        from company.models import Company
        from portfolio.models import WatchlistItem
        from research.models import ResearchSession

        result = await self.session.execute(select(WatchlistItem))
        items = list(result.scalars().all())
        if not items:
            return []

        all_tickers = [item.ticker for item in items]

        # 2. Batch companies by ticker
        comp_result = await self.session.execute(
            select(Company).where(Company.ticker.in_(all_tickers))
        )
        company_by_ticker: dict[str, Company] = {c.ticker: c for c in comp_result.scalars().all()}
        company_ids = [c.id for c in company_by_ticker.values()]

        # 3. Batch latest research per company
        research_by_company: dict[str, ResearchSession] = {}
        if company_ids:
            subq = (
                select(
                    ResearchSession.company_id,
                    func.max(ResearchSession.created_at).label("max_created"),
                )
                .where(ResearchSession.company_id.in_(company_ids))
                .group_by(ResearchSession.company_id)
                .subquery()
            )
            rs_result = await self.session.execute(
                select(ResearchSession).join(
                    subq,
                    (ResearchSession.company_id == subq.c.company_id)
                    & (ResearchSession.created_at == subq.c.max_created),
                )
            )
            for rs in rs_result.scalars().all():
                research_by_company[str(rs.company_id)] = rs

        # 4. Assemble (no per-item queries)
        reminders: list[dict[str, Any]] = []
        for item in items:
            company = company_by_ticker.get(item.ticker)
            if not company:
                continue

            research = research_by_company.get(str(company.id))
            days_since = None
            if research and research.created_at:
                delta = datetime.now(UTC) - research.created_at
                days_since = delta.days

            reasons = []
            if days_since and days_since > 30:
                reasons.append(f"距离上次研究 {days_since} 天")

            if reasons:
                reminders.append(
                    {
                        "ticker": item.ticker,
                        "company_name": company.name,
                        "days_since_research": days_since,
                        "reasons": reasons,
                        "priority": item.priority,
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
        from company.models import Company
        from market.models import StockPrice

        result = await self.session.execute(select(Company).where(Company.is_active.is_(True)))
        companies = list(result.scalars().all())
        if not companies:
            return []

        tickers = [c.ticker for c in companies]

        # Single batch query: all prices from last 90 days
        price_result = await self.session.execute(
            select(StockPrice)
            .where(
                StockPrice.ticker.in_(tickers),
                StockPrice.date >= func.current_date() - text("interval '90 days'"),
            )
            .order_by(StockPrice.ticker, StockPrice.date.desc())
        )
        all_prices = list(price_result.scalars().all())

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
