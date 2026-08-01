"""Scheduled job: two-layer morning brief generation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, func, select, text

from company.models import Company
from core.adapters.llm import create_llm
from core.database import managed_session
from core.interfaces import LLMMessage
from core.logging import logger
from core.morning_brief import MorningBrief
from core.news_fetcher import fetch_news_akshare, fetch_newsnow
from research.models import ResearchSession

OVERVIEW_PROMPT = (
    "你是一个简洁的投资分析助手。基于以下关注股票的20个交易日数据，生成一份中文市场速览。\n"
    "\n"
    "要求：\n"
    "1. 先写一段1-2句的总览（共关注几只股票，涨跌各几只）\n"
    "2. 然后每只股票独立成段，用「**股票代码 股票名**」开头\n"
    "3. 每只股票分析：当日涨跌、近一月趋势、值得注意的形态或新闻\n"
    "\n"
    "全程用中文，数据具体，不编造。"
)


STOCK_BRIEF_PROMPT = (
    "你是一个投资研究分析师。基于以下单只股票的20个交易日数据，写一段3-5句话的中文分析：\n"
    "\n"
    "1. **近期趋势** — 近一月走势如何？上涨/下跌/横盘？\n"
    "2. **关键信号** — 加速/反转/整理？\n"
    "3. **关注什么** — 什么信号会改变判断？\n"
    "\n"
    "股票：{ticker} ({name})\n"
    "最新价：{price}\n"
    "今日涨跌：{change}\n"
    "月度趋势（20日）：{monthly_trend}%\n"
    "距上次研究：{research_days} 天\n"
    "进行中研究：{open_sessions} 个\n"
    "相关新闻：{news}\n"
    "\n"
    "要求：全程用中文，数据具体，避免空泛建议。"
)


FOCUS_THRESHOLD_CHANGE = 3.0
FOCUS_THRESHOLD_DAYS = 30


async def morning_brief() -> dict:
    """Two-layer morning brief: overview + per-stock deep dives for focus stocks."""
    async with managed_session() as session:
        # 1. Watched companies == is_active (watchlist merged into Company).
        wl_result = await session.execute(
            select(Company).where(Company.is_active.is_(True))
        )
        watchlist_tickers = [c.ticker for c in wl_result.scalars().all()]

        # 2. Batch query: fetch ALL prices, companies, and research data at once
        active_tickers = watchlist_tickers[:20]
        if not active_tickers:
            brief_content = "关注列表为空，无法生成晨间简报。请先在投资组合中添加自选股。"
            return await _store_brief(session, brief_content, 0, 0)

        # 2a. Prices: one query for all tickers (latest per ticker via DISTINCT ON)
        price_result = await session.execute(
            text("""
                SELECT DISTINCT ON (sp.ticker) sp.id, sp.ticker, sp.date,
                       sp.open, sp.high, sp.low, sp.close, sp.volume
                FROM market.stock_prices sp
                WHERE sp.ticker = ANY(:tickers)
                ORDER BY sp.ticker, sp.date DESC
            """),
            {"tickers": active_tickers},
        )
        latest_prices: dict[str, dict] = {}
        for row in price_result.all():
            latest_prices[row.ticker] = {
                "close": row.close,
                "date": row.date,
                "open": row.open,
                "high": row.high,
                "low": row.low,
            }

        # Get 20-day windows per ticker (one batch query)
        all_price_rows = await session.execute(
            text("""
                SELECT sp.ticker, sp.date, sp.close
                FROM market.stock_prices sp
                WHERE sp.ticker = ANY(:tickers)
                ORDER BY sp.ticker, sp.date DESC
            """),
            {"tickers": active_tickers},
        )
        ticker_prices: dict[str, list[dict]] = {}
        for row in all_price_rows.all():
            ticker_prices.setdefault(row.ticker, []).append(
                {
                    "date": row.date,
                    "close": row.close,
                }
            )
        for t in ticker_prices:
            ticker_prices[t] = ticker_prices[t][:20]

        # 2b. Companies: one query
        comp_result = await session.execute(
            select(Company).where(Company.ticker.in_(active_tickers))
        )
        companies_by_ticker: dict[str, Company] = {c.ticker: c for c in comp_result.scalars().all()}

        # 2c. Research sessions: latest + open counts per company
        company_ids = [c.id for c in companies_by_ticker.values() if c.id]
        research_last: dict[uuid.UUID, ResearchSession] = {}
        if company_ids:
            rs_result = await session.execute(
                select(ResearchSession)
                .where(ResearchSession.company_id.in_(company_ids))
                .order_by(ResearchSession.company_id, desc(ResearchSession.created_at))
            )
            for rs in rs_result.scalars().all():
                if rs.company_id is None:
                    continue
                if rs.company_id not in research_last:
                    research_last[rs.company_id] = rs

        open_count_map: dict[uuid.UUID, int] = {}
        if company_ids:
            count_result = await session.execute(
                select(ResearchSession.company_id, func.count(ResearchSession.id))
                .where(
                    ResearchSession.company_id.in_(company_ids),
                    ResearchSession.status.in_(["draft", "researching", "reviewing"]),
                )
                .group_by(ResearchSession.company_id)
            )
            for cid, cnt in count_result.all():
                open_count_map[cid] = cnt

        # 3. Assemble stock_data from batch results
        # Fetch per-ticker news concurrently (each call spawns an akshare
        # subprocess — sequential calls would add up to minutes).
        news_results: dict[str, list[dict]] = {}
        if active_tickers:
            gathered = await asyncio.gather(
                *[fetch_news_akshare(t) for t in active_tickers],
                return_exceptions=True,
            )
            for ticker, res in zip(active_tickers, gathered):
                if isinstance(res, BaseException):
                    logger.debug("No news for %s (non-critical)", ticker)
                    news_results[ticker] = []
                else:
                    news_results[ticker] = res or []

        stock_data: list[dict] = []
        for ticker in active_tickers:
            company = companies_by_ticker.get(ticker)
            cname = company.name if company else ticker
            prices_20 = ticker_prices.get(ticker, [])
            if not prices_20:
                continue

            latest = prices_20[0]
            prev = prices_20[1] if len(prices_20) >= 2 else None
            oldest = prices_20[-1] if len(prices_20) >= 20 else None

            change_pct = None
            if prev and prev["close"]:
                change_pct = round(((latest["close"] - prev["close"]) / prev["close"]) * 100, 2)

            monthly_trend = None
            if oldest and oldest["close"]:
                monthly_trend = round(
                    ((latest["close"] - oldest["close"]) / oldest["close"]) * 100, 2
                )

            days_since = None
            open_count = 0
            if company and company.id:
                last_rs = research_last.get(company.id)
                if last_rs and last_rs.created_at:
                    days_since = (datetime.now(UTC) - last_rs.created_at).days
                open_count = open_count_map.get(company.id, 0)

            news_headlines = [n["title"] for n in news_results.get(ticker, [])[:3]]

            stock_data.append(
                {
                    "ticker": ticker,
                    "name": cname,
                    "price": latest["close"],
                    "change_pct": change_pct,
                    "monthly_trend": monthly_trend,
                    "days_since_research": days_since,
                    "open_research": open_count,
                    "sector": company.sector if company else None,
                    "news": news_headlines,
                }
            )

        if not stock_data:
            brief_content = "关注列表为空，无法生成晨间简报。请先在投资组合中添加自选股。"
            return await _store_brief(session, brief_content, 0, 0)

        llm = create_llm()

        # Layer 1: Market overview (single LLM call)
        watchlist_sectors = list(set(s.get("sector", "") for s in stock_data if s.get("sector")))
        market_news = await fetch_newsnow(sectors=watchlist_sectors)

        overview_lines = []
        for s in stock_data:
            chg = f" (今日 {s['change_pct']:+.2f}%)" if s["change_pct"] is not None else ""
            trend = f" 月趋势 {s['monthly_trend']:+.2f}%" if s["monthly_trend"] is not None else ""
            news_str = ""
            if s.get("news"):
                news_str = " 新闻: " + " | ".join(s["news"])
            overview_lines.append(
                f"  {s['ticker']} ({s['name']}): {s['price']:.2f}{chg}{trend}{news_str}"
            )
        overview_input = "Watchlist stocks (20-day data each):\n---\n" + "\n---\n".join(
            overview_lines
        )
        if market_news:
            overview_input += "\n\nGeneral financial news:\n" + "\n".join(
                f"  - {h}" for h in market_news[:5]
            )

        try:
            resp = await llm.generate(
                messages=[
                    LLMMessage(
                        role="user",
                        content=f"{OVERVIEW_PROMPT}\n\n{overview_input}",
                    )
                ],
                temperature=0.3,
                max_tokens=512,
            )
            overview = resp.content
        except Exception:
            logger.debug("Morning brief overview generation failed, using fallback")
            overview = f"关注 {len(stock_data)} 只股票。" + (
                f"上涨 {sum(1 for s in stock_data if s['change_pct'] and s['change_pct'] > 0)} 只，"
                f"下跌 {sum(1 for s in stock_data if s['change_pct'] and s['change_pct'] < 0)} 只。"
            )

        # Layer 2: Per-stock briefs for focus stocks (max 3)
        focus_stocks = [
            s
            for s in stock_data
            if (
                (s["change_pct"] is not None and abs(s["change_pct"]) >= FOCUS_THRESHOLD_CHANGE)
                or (
                    s["days_since_research"] is not None
                    and s["days_since_research"] >= FOCUS_THRESHOLD_DAYS
                )
            )
        ]
        focus_stocks.sort(key=lambda s: abs(s["change_pct"] or 0), reverse=True)
        focus_stocks = focus_stocks[:3]

        stock_briefs: list[dict] = []
        for s in focus_stocks:
            news_text = "; ".join(s.get("news", [])[:2]) or "暂无"
            prompt = STOCK_BRIEF_PROMPT.format(
                ticker=s["ticker"],
                name=s["name"],
                price=s["price"],
                change=(f"{s['change_pct']:+.2f}%" if s["change_pct"] is not None else "N/A"),
                monthly_trend=(
                    f"{s['monthly_trend']:+.2f}" if s["monthly_trend"] is not None else "N/A"
                ),
                research_days=s["days_since_research"] or "unknown",
                open_sessions=s["open_research"],
                news=news_text,
            )
            try:
                resp = await llm.generate(
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.3,
                    max_tokens=512,
                )
                stock_briefs.append(
                    {
                        "ticker": s["ticker"],
                        "name": s["name"],
                        "brief": resp.content,
                    }
                )
            except Exception:
                logger.debug("Stock brief LLM call failed for %s (non-critical)", s["ticker"])

        # Assemble final brief
        parts = [f"## 市场速览\n{overview}\n"]

        if stock_briefs:
            parts.append("## 重点分析\n")
            for sb in stock_briefs:
                parts.append(f"### {sb['ticker']} ({sb['name']})\n{sb['brief']}\n")

        if market_news:
            parts.append("## 📰 财经要闻\n")
            for h in market_news[:5]:
                parts.append(f"- {h}")
            parts.append("")

        parts.append("## 持仓一览\n")
        for s in stock_data:
            chg = f" ({s['change_pct']:+.2f}%)" if s["change_pct"] is not None else ""
            trend = f" 月 {s['monthly_trend']:+.2f}%" if s["monthly_trend"] is not None else ""
            research = ""
            if s["days_since_research"] is not None:
                research = f" [研究 {s['days_since_research']}d]"
            news_str = ""
            if s.get("news"):
                news_str = f" 📰 {s['news'][0][:40]}"
            parts.append(
                f"- {s['ticker']} ({s['name']}): {s['price']:.2f}{chg}{trend}{research}{news_str}"
            )

        brief_content = "\n".join(parts)
        logger.info(
            "Morning brief: %d stocks, %d focus, %d chars",
            len(stock_data),
            len(stock_briefs),
            len(brief_content),
        )

        return await _store_brief(session, brief_content, len(stock_data), len(stock_briefs))


async def _store_brief(session, content: str, stocks: int, focus: int) -> dict:
    """Store brief in MorningBrief table and return response."""
    brief = MorningBrief(
        content=content,
        char_count=len(content),
        stocks_covered=stocks,
        focus_stocks=focus,
    )
    session.add(brief)
    await session.commit()
    return {
        "status": "ok",
        "char_count": len(content),
        "stocks_covered": stocks,
        "focus_stocks": focus,
        "preview": content[:200],
    }
