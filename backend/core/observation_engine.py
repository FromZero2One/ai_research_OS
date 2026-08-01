"""Observation Engine — scans watchlist items daily for signals.

Outputs observations stored in EventLog that feed:
  - Research reminders (Dashboard)
  - Morning Brief content
  - Watchlist status updates
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from core.logging import logger

OBSERVATION_THRESHOLDS = {
    "research_days_warning": 14,  # → attention after 14 days
    "research_days_critical": 30,  # → need_research after 30 days
    "price_change_pct": 5.0,  # significant price change threshold
}


async def run_observation_cycle() -> dict:
    """Main observation cycle — scan all watchlist items for signals.

    Called by scheduler (daily) or manually via API.
    Returns summary of observations generated.
    """
    from sqlalchemy import desc, select

    from company.models import Company
    from core.database import managed_session
    from research.models import ResearchSession

    async with managed_session() as session:
        observations = []

        # Watched companies == is_active (watchlist merged into Company).
        result = await session.execute(select(Company).where(Company.is_active.is_(True)))
        all_items = list(result.scalars().all())

        if not all_items:
            logger.info("Observation: no watched companies to scan")
            return {"status": "ok", "items_scanned": 0, "observations": 0}

        logger.info("Observation: scanning %d watched companies", len(all_items))

        tickers = [item.ticker for item in all_items]
        companies_result = await session.execute(select(Company).where(Company.ticker.in_(tickers)))
        companies_by_ticker: dict[str, Company] = {
            c.ticker: c for c in companies_result.scalars().all()
        }

        # ── Batch preload: latest 2 prices per ticker ─────────────────
        from sqlalchemy import text as sa_text

        prices_result = await session.execute(
            sa_text("""
                SELECT p.ticker, p.date, p.close
                FROM market.stock_prices p
                WHERE p.ticker = ANY(:tickers)
                ORDER BY p.ticker, p.date DESC
            """),
            {"tickers": tickers},
        )
        ticker_prices: dict[str, list[dict]] = {}
        for row in prices_result.all():
            ticker_prices.setdefault(row.ticker, []).append({"date": row.date, "close": row.close})

        # ── Batch preload: latest research per company ────────────────
        company_ids = [c.id for c in companies_by_ticker.values() if c.id]
        latest_research_by_company: dict[uuid.UUID, ResearchSession] = {}
        if company_ids:
            rs_result = await session.execute(
                select(ResearchSession)
                .where(ResearchSession.company_id.in_(company_ids))
                .order_by(ResearchSession.company_id, desc(ResearchSession.created_at))
            )
            for rs in rs_result.scalars().all():
                if rs.company_id is None:
                    continue
                if rs.company_id not in latest_research_by_company:
                    latest_research_by_company[rs.company_id] = rs

        # ── Batch preload: sectors → companies in same sector ─────────
        sectors: set[str] = set()
        for c in companies_by_ticker.values():
            if c.sector:
                sectors.add(c.sector)
        sector_companies_map: dict[str, list[Company]] = {}
        if sectors:
            sc_result = await session.execute(
                select(Company).where(
                    Company.sector.in_(list(sectors)),
                    Company.is_active.is_(True),
                )
            )
            for sc in sc_result.scalars().all():
                if sc.sector:
                    sector_companies_map.setdefault(sc.sector, []).append(sc)

        # ── Main loop: all DB lookups are now dict lookups ────────────
        for item in all_items:
            ticker = item.ticker
            reasons: list[str] = []

            company = companies_by_ticker.get(ticker)
            if not company:
                continue

            # Research freshness check
            latest_research = latest_research_by_company.get(company.id) if company.id else None
            days_since_research = None
            if latest_research and latest_research.created_at:
                delta = datetime.now(UTC) - latest_research.created_at
                days_since_research = delta.days

            if days_since_research is not None:
                if days_since_research >= OBSERVATION_THRESHOLDS["research_days_critical"]:
                    reasons.append(
                        f"距上次研究 {days_since_research} 天"
                        f"（超过 {OBSERVATION_THRESHOLDS['research_days_critical']} 天）"
                    )
                elif days_since_research >= OBSERVATION_THRESHOLDS["research_days_warning"]:
                    reasons.append(
                        f"距上次研究 {days_since_research} 天"
                        f"（超过 {OBSERVATION_THRESHOLDS['research_days_warning']} 天）"
                    )

            # Price change check
            prices_2 = ticker_prices.get(ticker, [])
            significant_move = False
            if len(prices_2) >= 2:
                p0, p1 = prices_2[0], prices_2[1]
                if p1["close"]:
                    recent_change = abs((p0["close"] - p1["close"]) / p1["close"] * 100)
                    if recent_change >= OBSERVATION_THRESHOLDS["price_change_pct"]:
                        direction = "上涨" if p0["close"] > p1["close"] else "下跌"
                        reasons.append(f"价格显著{direction} {recent_change:.1f}%")
                        significant_move = True

            # Sector-level alert
            if significant_move and company.sector:
                related = sector_companies_map.get(company.sector, [])
                for sc in related[:3]:
                    if sc.ticker == ticker:
                        continue
                    reasons.append(
                        f"同板块 「{company.sector}」 {ticker} 异动，建议关注 {sc.ticker}"
                    )

            # Store observation if any signals found
            if reasons:
                observations.append(
                    {
                        "ticker": ticker,
                        "company_name": company.name,
                        "reasons": reasons,
                        "days_since_research": days_since_research,
                    }
                )

                from core.observation import Observation

                obs_status = (
                    "need_research"
                    if days_since_research
                    and days_since_research >= OBSERVATION_THRESHOLDS["research_days_critical"]
                    else "attention"
                )
                session.add(
                    Observation(
                        ticker=ticker,
                        company_name=company.name,
                        reasons="\n".join(reasons),
                        status=obs_status,
                        days_since_research=days_since_research,
                    )
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
    """Fetch recent observations from Observation table."""
    from sqlalchemy import desc, select

    from core.database import managed_session
    from core.observation import Observation

    async with managed_session() as session:
        result = await session.execute(
            select(Observation).order_by(desc(Observation.observed_at)).limit(limit)
        )
        entries = list(result.scalars().all())

        return [
            {
                "id": str(e.id),
                "ticker": e.ticker,
                "company_name": e.company_name,
                "reasons": e.reasons.split("\n"),
                "status": e.status,
                "observed_at": e.observed_at.isoformat() if e.observed_at else None,
            }
            for e in entries
        ]
