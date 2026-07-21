"""Scheduled job implementations — market data, morning brief, etc.

Each function is an async callable registered via scheduler.register_job().
"""

from __future__ import annotations

from core.logging import logger


# ── Market Data Update ──────────────────────────────────────────────

async def market_data_update() -> dict:
    """Daily: Pull latest market data for all tracked companies.

    For A-stocks: sync from akshare MySQL.
    For US stocks: data is already seeded; this is a placeholder for
    a future yfinance/API integration.
    """
    from core.database import async_session_factory
    from market.service import MarketService

    async with async_session_factory() as session:
        market = MarketService(session)

        # Get all companies with tickers
        from sqlalchemy import select
        from company.models import Company

        result = await session.execute(select(Company.ticker).where(Company.is_active == True))
        tickers = [row[0] for row in result.all()]
        logger.info("Market data update: %d companies to check", len(tickers))

        updated = 0
        for ticker in tickers:
            try:
                prices = await market.get_prices(ticker, limit=5)
                if prices:
                    updated += 1
            except Exception as e:
                logger.debug("Skipping %s: %s", ticker, e)

        logger.info("Market data update: %d/%d tickers updated", updated, len(tickers))
        return {"tickers_checked": len(tickers), "updated": updated}


# ── Morning Brief ───────────────────────────────────────────────────

MORNING_BRIEF_SYSTEM_PROMPT = """Generate a concise morning investment brief based on the data provided.

Include:
1. **Market Overview** — Key market movements
2. **Company Updates** — Notable changes for tracked companies
3. **Research Reminders** — Open research sessions that need attention

Keep it under 500 words. Be specific with numbers and facts."""


async def morning_brief() -> dict:
    """Daily: Generate morning brief using AI with latest data."""
    from core.adapters.llm import create_llm
    from core.database import async_session_factory
    from core.interfaces import LLMMessage
    from sqlalchemy import desc, select

    async with async_session_factory() as session:
        # 1. Gather recent market data
        from market.models import StockPrice

        result = await session.execute(
            select(StockPrice).order_by(desc(StockPrice.date)).limit(5)
        )
        recent_prices = result.scalars().all()

        market_summary = "Recent prices:\n"
        tickers_seen = set()
        for p in recent_prices:
            if p.ticker not in tickers_seen:
                market_summary += f"  {p.ticker}: Close={p.close:.2f} ({p.date})\n"
                tickers_seen.add(p.ticker)

        # 2. Gather open research sessions
        from research.models import ResearchSession

        result = await session.execute(
            select(ResearchSession).where(
                ResearchSession.status.in_(["draft", "researching", "reviewing"])
            ).order_by(ResearchSession.created_at.desc()).limit(10)
        )
        open_sessions = result.scalars().all()

        session_summary = "\nOpen research:\n"
        for s in open_sessions:
            session_summary += f"  [{s.status}] {s.title}\n"

        # 3. Call LLM
        llm = create_llm()
        messages = [
            LLMMessage(role="system", content=MORNING_BRIEF_SYSTEM_PROMPT),
            LLMMessage(role="user", content=f"{market_summary}\n{session_summary}"),
        ]
        response = await llm.generate(messages=messages, temperature=0.3, max_tokens=2048)

        # 4. Store brief (in memory / could save to DB)
        brief_content = response.content

        logger.info("Morning brief generated (%d chars)", len(brief_content))

        # Store in event log
        from core.event_service import EventLogger
        event_logger = EventLogger(session)
        await event_logger.record(
            source="scheduler",
            event_type="morning_brief.generated",
            entity_type="brief",
            entity_id="daily",
            payload={"content": brief_content[:2000], "char_count": len(brief_content)},
        )
        await session.commit()

        return {
            "status": "ok",
            "char_count": len(brief_content),
            "preview": brief_content[:200],
        }
