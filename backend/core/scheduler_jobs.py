"""Scheduled job implementations — market data, morning brief, etc.

Each function is an async callable registered via scheduler.register_job().
"""

from __future__ import annotations

from datetime import datetime, timezone

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

OVERVIEW_PROMPT = """You are a concise investment assistant. Based on the watchlist data below, write a very brief market overview (2-3 sentences).

Focus on:
- How many stocks are up/down
- Which sector saw the most movement
- Any notable changes

Keep it to 2-3 sentences. Be specific with numbers."""

STOCK_BRIEF_PROMPT = """You are an investment research assistant. Based on the following data for a single stock, write a 3-5 sentence brief covering:

1. What happened (price change)
2. Why it might matter (context)
3. What to watch for (key signal)

Stock: {ticker} ({name})
Latest price: {price}
Change: {change}
Days since last research: {research_days}
Open research sessions for this company: {open_sessions}

Be concise and specific."""


async def morning_brief() -> dict:
    """Two-layer morning brief: overview + per-stock deep dives for focus stocks."""
    import json
    from core.adapters.llm import create_llm
    from core.database import async_session_factory
    from core.interfaces import LLMMessage
    from sqlalchemy import desc, select
    from sqlalchemy.orm import selectinload

    async with async_session_factory() as session:
        from market.models import StockPrice
        from company.models import Company
        from portfolio.models import Watchlist
        from research.models import ResearchSession

        # 1. Collect all watchlist tickers
        watchlist_tickers: list[str] = []
        wl_result = await session.execute(
            select(Watchlist).options(selectinload(Watchlist.items))
        )
        for wl in wl_result.scalars().all():
            watchlist_tickers.extend(item.ticker for item in wl.items)
        watchlist_tickers = list(set(watchlist_tickers))

        # 2. Fetch price + research data for each stock
        stock_data: list[dict] = []
        for ticker in watchlist_tickers[:20]:
            prices = await session.execute(
                select(StockPrice)
                .where(StockPrice.ticker == ticker)
                .order_by(desc(StockPrice.date))
                .limit(2)
            )
            rows = list(prices.scalars().all())
            if not rows:
                continue

            comp = await session.execute(
                select(Company).where(Company.ticker == ticker).limit(1)
            )
            company = comp.scalar_one_or_none()
            cname = company.name if company else ticker

            # Price change
            latest = rows[0]
            change_pct = None
            if len(rows) >= 2 and rows[1].close:
                change_pct = round(((latest.close - rows[1].close) / rows[1].close) * 100, 2)

            # Days since last research
            days_since = None
            if company:
                rs = await session.execute(
                    select(ResearchSession)
                    .where(ResearchSession.company_id == company.id)
                    .order_by(desc(ResearchSession.created_at))
                    .limit(1)
                )
                last = rs.scalar_one_or_none()
                if last and last.created_at:
                    days_since = (datetime.now(timezone.utc) - last.created_at).days

            # Open research sessions for this company
            open_count = 0
            if company:
                rc = await session.execute(
                    select(ResearchSession).where(
                        ResearchSession.company_id == company.id,
                        ResearchSession.status.in_(["draft", "researching", "reviewing"]),
                    )
                )
                open_count = len(list(rc.scalars().all()))

            stock_data.append({
                "ticker": ticker,
                "name": cname,
                "price": latest.close,
                "change_pct": change_pct,
                "days_since_research": days_since,
                "open_research": open_count,
                "sector": company.sector if company else None,
            })

        if not stock_data:
            brief_content = "关注列表为空，无法生成晨间简报。请先在投资组合中添加自选股。"
            return _store_brief(session, brief_content, 0, 0)

        llm = create_llm()

        # 3. Layer 1: Market overview (single LLM call)
        overview_lines = []
        for s in stock_data:
            chg = f" ({s['change_pct']:+.2f}%)" if s['change_pct'] is not None else ""
            overview_lines.append(f"  {s['ticker']} ({s['name']}): {s['price']:.2f}{chg}")
        overview_input = "Watchlist:\n" + "\n".join(overview_lines)

        try:
            resp = await llm.generate(
                messages=[LLMMessage(role="user", content=f"{OVERVIEW_PROMPT}\n\n{overview_input}")],
                temperature=0.3, max_tokens=512,
            )
            overview = resp.content
        except Exception:
            overview = f"关注 {len(stock_data)} 只股票。" + (
                f"上涨 {sum(1 for s in stock_data if s['change_pct'] and s['change_pct'] > 0)} 只，"
                f"下跌 {sum(1 for s in stock_data if s['change_pct'] and s['change_pct'] < 0)} 只。"
            )

        # 4. Layer 2: Per-stock briefs for focus stocks (max 3)
        focus_stocks = [s for s in stock_data if (
            (s['change_pct'] is not None and abs(s['change_pct']) >= 3) or
            (s['days_since_research'] is not None and s['days_since_research'] >= 30)
        )]
        focus_stocks.sort(key=lambda s: abs(s['change_pct'] or 0), reverse=True)
        focus_stocks = focus_stocks[:3]

        stock_briefs: list[dict] = []
        for s in focus_stocks:
            prompt = STOCK_BRIEF_PROMPT.format(
                ticker=s['ticker'], name=s['name'], price=s['price'],
                change=f"{s['change_pct']:+.2f}%" if s['change_pct'] is not None else "N/A",
                research_days=s['days_since_research'] or "unknown",
                open_sessions=s['open_research'],
            )
            try:
                resp = await llm.generate(
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.3, max_tokens=512,
                )
                stock_briefs.append({"ticker": s['ticker'], "name": s['name'], "brief": resp.content})
            except Exception:
                pass

        # 5. Assemble final brief
        parts = [f"## 市场速览\n{overview}\n"]

        if stock_briefs:
            parts.append("## 重点分析\n")
            for sb in stock_briefs:
                parts.append(f"### {sb['ticker']} ({sb['name']})\n{sb['brief']}\n")

        parts.append("## 持仓一览\n")
        for s in stock_data:
            chg = f" ({s['change_pct']:+.2f}%)" if s['change_pct'] is not None else ""
            research = ""
            if s['days_since_research'] is not None:
                research = f" [研究 {s['days_since_research']}d]"
            parts.append(f"- {s['ticker']} ({s['name']}): {s['price']:.2f}{chg}{research}")

        brief_content = "\n".join(parts)
        logger.info("Morning brief: %d stocks, %d focus, %d chars",
                     len(stock_data), len(stock_briefs), len(brief_content))

        # 6. Store
        return await _store_brief(session, brief_content, len(stock_data), len(stock_briefs))


async def _store_brief(session, content: str, stocks: int, focus: int) -> dict:
    """Store brief in EventLog and return response."""
    from core.event_service import EventLogger
    event_logger = EventLogger(session)
    await event_logger.record(
        source="scheduler",
        event_type="morning_brief.generated",
        entity_type="brief",
        entity_id="daily",
        payload={"content": content[:3000], "char_count": len(content), "stocks": stocks, "focus_stocks": focus},
    )
    await session.commit()
    return {
        "status": "ok", "char_count": len(content),
        "stocks_covered": stocks, "focus_stocks": focus,
        "preview": content[:200],
    }
