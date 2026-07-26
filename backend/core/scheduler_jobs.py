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
    """Daily: Generate morning brief using AI with watchlist + price data."""
    from core.adapters.llm import create_llm
    from core.database import async_session_factory
    from core.interfaces import LLMMessage
    from sqlalchemy import desc, select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as session:
        # 1. Collect watchlist tickers (user's tracked stocks)
        from portfolio.models import Watchlist
        watchlist_tickers: list[str] = []
        wl_result = await session.execute(
            select(Watchlist).options(selectinload(Watchlist.items))
        )
        for wl in wl_result.scalars().all():
            watchlist_tickers.extend(item.ticker for item in wl.items)
        watchlist_tickers = list(set(watchlist_tickers))  # dedup

        # 2. Fetch latest 2 prices per watchlist stock (for change %)
        from market.models import StockPrice
        from company.models import Company

        market_lines: list[str] = []
        for ticker in watchlist_tickers[:15]:  # max 15 stocks
            prices = await session.execute(
                select(StockPrice)
                .where(StockPrice.ticker == ticker)
                .order_by(desc(StockPrice.date))
                .limit(2)
            )
            rows = list(prices.scalars().all())
            if not rows:
                continue

            # Get company name
            comp = await session.execute(
                select(Company.name).where(Company.ticker == ticker).limit(1)
            )
            cname = comp.scalar_one_or_none() or ticker

            latest = rows[0]
            change_str = ""
            if len(rows) >= 2:
                prev = rows[1].close
                if prev:
                    chg = ((latest.close - prev) / prev) * 100
                    change_str = f" ({chg:+.2f}%)"

            market_lines.append(f"  {ticker} ({cname}): {latest.close:.2f}{change_str}")

        market_summary = "Watchlist prices:\n" + "\n".join(market_lines) if market_lines else "No watchlist data."

        # 3. Gather open research sessions
        from research.models import ResearchSession
        result = await session.execute(
            select(ResearchSession).where(
                ResearchSession.status.in_(["draft", "researching", "reviewing"])
            ).order_by(ResearchSession.created_at.desc()).limit(10)
        )
        open_sessions = list(result.scalars().all())

        session_lines: list[str] = []
        for s in open_sessions:
            # Get company name
            cname = ""
            if s.company_id:
                comp = await session.execute(
                    select(Company.name).where(Company.id == s.company_id).limit(1)
                )
                cname = f" ({comp.scalar_one_or_none() or ''})"
            session_lines.append(f"  [{s.status}] {s.title}{cname}")
        session_summary = "\nResearch in progress:\n" + "\n".join(session_lines) if session_lines else ""

        # 4. Call LLM
        llm = create_llm()
        user_content = f"{market_summary}\n{session_summary}" if session_summary else market_summary
        messages = [
            LLMMessage(role="system", content=MORNING_BRIEF_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_content),
        ]
        response = await llm.generate(messages=messages, temperature=0.3, max_tokens=2048)
        brief_content = response.content

        logger.info("Morning brief generated (%d chars, %d stocks, %d open research)",
                     len(brief_content), len(market_lines), len(open_sessions))

        # 5. Store in event log
        from core.event_service import EventLogger
        event_logger = EventLogger(session)
        await event_logger.record(
            source="scheduler",
            event_type="morning_brief.generated",
            entity_type="brief",
            entity_id="daily",
            payload={
                "content": brief_content[:2000],
                "char_count": len(brief_content),
                "stocks_covered": len(market_lines),
                "open_research": len(open_sessions),
            },
        )
        await session.commit()

        return {
            "status": "ok",
            "char_count": len(brief_content),
            "stocks_covered": len(market_lines),
            "open_research": len(open_sessions),
            "preview": brief_content[:200],
        }
