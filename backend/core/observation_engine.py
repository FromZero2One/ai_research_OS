"""Observation Engine — scans watchlist items daily for signals.

Outputs observations stored in EventLog that feed:
  - Research reminders (Dashboard)
  - Morning Brief content
  - Watchlist status updates
"""

from __future__ import annotations

from datetime import datetime, timezone

from core.logging import logger


OBSERVATION_THRESHOLDS = {
    "research_days_warning": 14,   # → attention after 14 days
    "research_days_critical": 30,  # → need_research after 30 days
    "price_change_pct": 5.0,       # significant price change threshold
}


async def run_observation_cycle() -> dict:
    """Main observation cycle — scan all watchlist items for signals.

    Called by scheduler (daily) or manually via API.
    Returns summary of observations generated.
    """
    from core.database import async_session_factory
    from core.event_service import EventLogger
    from sqlalchemy import desc, select
    from sqlalchemy.orm import selectinload

    from company.models import Company
    from market.models import StockPrice
    from portfolio.models import Watchlist, WatchlistItem
    from research.models import ResearchSession

    async with async_session_factory() as session:
        event_logger = EventLogger(session)
        observations = []

        # Get all watchlist items
        result = await session.execute(
            select(Watchlist).options(selectinload(Watchlist.items))
        )
        watchlists = list(result.scalars().all())

        all_items: list[WatchlistItem] = []
        for wl in watchlists:
            all_items.extend(wl.items)

        if not all_items:
            logger.info("Observation: no watchlist items to scan")
            return {"status": "ok", "items_scanned": 0, "observations": 0}

        logger.info("Observation: scanning %d watchlist items", len(all_items))

        for item in all_items:
            ticker = item.ticker
            reasons: list[str] = []

            # 1. Get company info
            company_result = await session.execute(
                select(Company).where(Company.ticker == ticker).limit(1)
            )
            company = company_result.scalar_one_or_none()
            if not company:
                continue

            # 2. Check last research date
            research_result = await session.execute(
                select(ResearchSession)
                .where(ResearchSession.company_id == company.id)
                .order_by(desc(ResearchSession.created_at))
                .limit(1)
            )
            latest_research = research_result.scalar_one_or_none()

            days_since_research = None
            if latest_research and latest_research.created_at:
                delta = datetime.now(timezone.utc) - latest_research.created_at
                days_since_research = delta.days

            if days_since_research is not None:
                if days_since_research >= OBSERVATION_THRESHOLDS["research_days_critical"]:
                    reasons.append(f"距上次研究 {days_since_research} 天（超过 {OBSERVATION_THRESHOLDS['research_days_critical']} 天）")
                elif days_since_research >= OBSERVATION_THRESHOLDS["research_days_warning"]:
                    reasons.append(f"距上次研究 {days_since_research} 天（超过 {OBSERVATION_THRESHOLDS['research_days_warning']} 天）")

            # 3. Check latest price change
            price_result = await session.execute(
                select(StockPrice)
                .where(StockPrice.ticker == ticker)
                .order_by(desc(StockPrice.date))
                .limit(2)
            )
            prices = list(price_result.scalars().all())

            if len(prices) >= 2:
                recent_change = abs((prices[0].close - prices[1].close) / prices[1].close * 100)
                if recent_change >= OBSERVATION_THRESHOLDS["price_change_pct"]:
                    direction = "上涨" if prices[0].close > prices[1].close else "下跌"
                    reasons.append(f"价格显著{direction} {recent_change:.1f}%")

            # 4. Store observation if any signals found
            if reasons:
                observations.append({
                    "ticker": ticker,
                    "company_name": company.name,
                    "reasons": reasons,
                    "days_since_research": days_since_research,
                })

                await event_logger.record(
                    source="observation",
                    event_type="observation.generated",
                    entity_type="watchlist_item",
                    entity_id=str(item.id),
                    payload={
                        "ticker": ticker,
                        "company_name": company.name,
                        "reasons": reasons,
                        "days_since_research": days_since_research,
                        "status": "need_research" if days_since_research and days_since_research >= OBSERVATION_THRESHOLDS["research_days_critical"] else "attention",
                    },
                )

        await session.commit()
        logger.info("Observation: %d observations from %d items", len(observations), len(all_items))

        return {
            "status": "ok",
            "items_scanned": len(all_items),
            "observations": len(observations),
            "details": observations[:10],  # preview
        }


async def get_recent_observations(limit: int = 20) -> list[dict]:
    """Fetch recent observations from EventLog."""
    from core.database import async_session_factory
    from core.event_log import EventLog
    from sqlalchemy import desc, select

    async with async_session_factory() as session:
        result = await session.execute(
            select(EventLog)
            .where(
                EventLog.source == "observation",
                EventLog.event_type == "observation.generated",
            )
            .order_by(desc(EventLog.occurred_at))
            .limit(limit)
        )
        entries = list(result.scalars().all())

        return [
            {
                "id": str(e.id),
                "ticker": e.payload.get("ticker") if e.payload else None,
                "company_name": e.payload.get("company_name") if e.payload else None,
                "reasons": e.payload.get("reasons") if e.payload else [],
                "status": e.payload.get("status") if e.payload else "attention",
                "observed_at": e.occurred_at.isoformat() if e.occurred_at else None,
            }
            for e in entries
        ]
