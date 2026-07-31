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
    from core.database import managed_session
    from market.service.price_service import PriceService

    async with managed_session() as session:
        market = PriceService(session)

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

OVERVIEW_PROMPT = """你是一个简洁的投资分析助手。基于以下关注股票的20个交易日数据，生成一份中文市场速览。

要求：
1. 先写一段1-2句的总览（共关注几只股票，涨跌各几只）
2. 然后每只股票独立成段，用「**股票代码 股票名**」开头
3. 每只股票分析：当日涨跌、近一月趋势、值得注意的形态或新闻

全程用中文，数据具体，不编造。"""

async def _fetch_newsnow(sectors: list[str] | None = None) -> list[str]:
    """Fetch financial news relevant to given sectors via persistent MCP."""
    from core.adapters.newsnow_mcp import get_headlines
    return await get_headlines(sectors=sectors)


async def _fetch_news_akshare(ticker: str) -> list[dict]:
    """Fetch stock news via akshare subprocess."""
    import asyncio
    import json as _json
    import os, subprocess as _sp

    AKSHARE_MCP_DIR = os.getenv("AKSHARE_MCP_DIR", "/home/wsm/codes/akshare_mcp")
    code = f"""
import json, sys
import akshare as ak
try:
    df = ak.stock_news_em(symbol='{ticker}')
    if df is None or df.empty:
        print("__R__:[]")
    else:
        rows = []
        for _, row in df.iterrows():
            rows.append({{"title": str(row.get("新闻标题", "")), "source": str(row.get("文章来源", ""))}})
        print("__R__:" + json.dumps(rows, ensure_ascii=False)[:2000])
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""
    env = os.environ.copy()
    for v in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        env.pop(v, None)
    try:
        result = _sp.run(
            ["uv", "run", "--directory", AKSHARE_MCP_DIR, "python", "-c", code],
            capture_output=True, text=True, timeout=30, env=env,
        )
        if result.returncode != 0:
            return []
        for line in result.stdout.splitlines():
            if line.startswith("__R__:"):
                return _json.loads(line[6:])
        return []
    except Exception:
        logger.debug("akshare news subprocess failed")
        return []


STOCK_BRIEF_PROMPT = """你是一个投资研究分析师。基于以下单只股票的20个交易日数据，写一段3-5句话的中文分析：

1. **近期趋势** — 近一月走势如何？上涨/下跌/横盘？
2. **关键信号** — 加速/反转/整理？
3. **关注什么** — 什么信号会改变判断？

股票：{ticker} ({name})
最新价：{price}
今日涨跌：{change}
月度趋势（20日）：{monthly_trend}%
距上次研究：{research_days} 天
进行中研究：{open_sessions} 个
相关新闻：{news}

要求：全程用中文，数据具体，避免空泛建议。"""

FOCUS_THRESHOLD_CHANGE = 3.0
FOCUS_THRESHOLD_DAYS = 30


async def morning_brief() -> dict:
    """Two-layer morning brief: overview + per-stock deep dives for focus stocks."""
    import json
    from core.adapters.llm import create_llm
    from core.database import managed_session
    from core.interfaces import LLMMessage
    from sqlalchemy import desc, select
    from sqlalchemy.orm import selectinload

    async with managed_session() as session:
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

        # 2. Batch query: fetch ALL prices, companies, and research data at once
        active_tickers = watchlist_tickers[:20]
        if not active_tickers:
            brief_content = "关注列表为空，无法生成晨间简报。请先在投资组合中添加自选股。"
            return _store_brief(session, brief_content, 0, 0)

        # 2a. Prices: one query for all tickers (latest 20 days each using DISTINCT ON / row_number)
        from sqlalchemy import text as sa_text

        price_result = await session.execute(
            sa_text(f"""
                SELECT DISTINCT ON (sp.ticker) sp.id, sp.ticker, sp.date,
                       sp.open, sp.high, sp.low, sp.close, sp.volume
                FROM market.stock_prices sp
                WHERE sp.ticker = ANY(:tickers)
                ORDER BY sp.ticker, sp.date DESC
            """),
            {"tickers": active_tickers},
        )
        # Get latest price per ticker
        latest_prices: dict[str, dict] = {}
        for row in price_result.all():
            latest_prices[row.ticker] = {
                "close": row.close, "date": row.date,
                "open": row.open, "high": row.high, "low": row.low,
            }

        # Get 20-day windows per ticker (one batch query)
        all_price_rows = await session.execute(
            sa_text(f"""
                SELECT sp.ticker, sp.date, sp.close
                FROM market.stock_prices sp
                WHERE sp.ticker = ANY(:tickers)
                ORDER BY sp.ticker, sp.date DESC
            """),
            {"tickers": active_tickers},
        )
        ticker_prices: dict[str, list[dict]] = {}
        for row in all_price_rows.all():
            ticker_prices.setdefault(row.ticker, []).append({
                "date": row.date, "close": row.close,
            })
        # Trim to 20 per ticker
        for t in ticker_prices:
            ticker_prices[t] = ticker_prices[t][:20]

        # 2b. Companies: one query
        comp_result = await session.execute(
            select(Company).where(Company.ticker.in_(active_tickers))
        )
        companies_by_ticker: dict[str, Company] = {
            c.ticker: c for c in comp_result.scalars().all()
        }

        # 2c. Research sessions: one query per company (collect company_ids)
        company_ids = [c.id for c in companies_by_ticker.values() if c.id]
        # Latest research per company
        research_last: dict[uuid.UUID, ResearchSession] = {}
        if company_ids:
            rs_result = await session.execute(
                select(ResearchSession)
                .where(ResearchSession.company_id.in_(company_ids))
                .order_by(ResearchSession.company_id, desc(ResearchSession.created_at))
            )
            for rs in rs_result.scalars().all():
                if rs.company_id not in research_last:
                    research_last[rs.company_id] = rs

        # Open research count per company
        open_count_map: dict[uuid.UUID, int] = {}
        if company_ids:
            from sqlalchemy import func as sa_func
            count_result = await session.execute(
                select(ResearchSession.company_id, sa_func.count(ResearchSession.id))
                .where(
                    ResearchSession.company_id.in_(company_ids),
                    ResearchSession.status.in_(["draft", "researching", "reviewing"]),
                )
                .group_by(ResearchSession.company_id)
            )
            for cid, cnt in count_result.all():
                open_count_map[cid] = cnt

        # 3. Assemble stock_data from batch results
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
                monthly_trend = round(((latest["close"] - oldest["close"]) / oldest["close"]) * 100, 2)

            days_since = None
            open_count = 0
            if company and company.id:
                last_rs = research_last.get(company.id)
                if last_rs and last_rs.created_at:
                    days_since = (datetime.now(timezone.utc) - last_rs.created_at).days
                open_count = open_count_map.get(company.id, 0)

            # Fetch latest news headlines via akshare
            news_headlines: list[str] = []
            try:
                ns = await _fetch_news_akshare(ticker)
                news_headlines = [n["title"] for n in ns[:3]]
            except Exception:
                logger.debug("No news for %s (non-critical)", ticker)

            stock_data.append({
                "ticker": ticker,
                "name": cname,
                "price": latest["close"],
                "change_pct": change_pct,
                "monthly_trend": monthly_trend,
                "days_since_research": days_since,
                "open_research": open_count,
                "sector": company.sector if company else None,
                "news": news_headlines,
            })

        if not stock_data:
            brief_content = "关注列表为空，无法生成晨间简报。请先在投资组合中添加自选股。"
            return _store_brief(session, brief_content, 0, 0)

        llm = create_llm()

        # 3. Layer 1: Market overview (single LLM call)
        # Collect unique sectors from watchlist for news filtering
        watchlist_sectors = list(set(s.get("sector", "") for s in stock_data if s.get("sector")))
        market_news = await _fetch_newsnow(sectors=watchlist_sectors)

        overview_lines = []
        for s in stock_data:
            chg = f" (今日 {s['change_pct']:+.2f}%)" if s['change_pct'] is not None else ""
            trend = f" 月趋势 {s['monthly_trend']:+.2f}%" if s['monthly_trend'] is not None else ""
            news_str = ""
            if s.get("news"):
                news_str = " 新闻: " + " | ".join(s["news"])
            overview_lines.append(f"  {s['ticker']} ({s['name']}): {s['price']:.2f}{chg}{trend}{news_str}")
        overview_input = "Watchlist stocks (20-day data each):\n---\n" + "\n---\n".join(overview_lines)
        if market_news:
            overview_input += "\n\nGeneral financial news:\n" + "\n".join(f"  - {h}" for h in market_news[:5])

        try:
            resp = await llm.generate(
                messages=[LLMMessage(role="user", content=f"{OVERVIEW_PROMPT}\n\n{overview_input}")],
                temperature=0.3, max_tokens=512,
            )
            overview = resp.content
        except Exception:
            logger.debug("Morning brief overview generation failed, using fallback")
            overview = f"关注 {len(stock_data)} 只股票。" + (
                f"上涨 {sum(1 for s in stock_data if s['change_pct'] and s['change_pct'] > 0)} 只，"
                f"下跌 {sum(1 for s in stock_data if s['change_pct'] and s['change_pct'] < 0)} 只。"
            )

        # 4. Layer 2: Per-stock briefs for focus stocks (max 3)
        focus_stocks = [s for s in stock_data if (
            (s['change_pct'] is not None and abs(s['change_pct']) >= FOCUS_THRESHOLD_CHANGE) or
            (s['days_since_research'] is not None and s['days_since_research'] >= FOCUS_THRESHOLD_DAYS)
        )]
        focus_stocks.sort(key=lambda s: abs(s['change_pct'] or 0), reverse=True)
        focus_stocks = focus_stocks[:3]

        stock_briefs: list[dict] = []
        for s in focus_stocks:
            news_text = "; ".join(s.get("news", [])[:2]) or "暂无"
            prompt = STOCK_BRIEF_PROMPT.format(
                ticker=s['ticker'], name=s['name'], price=s['price'],
                change=f"{s['change_pct']:+.2f}%" if s['change_pct'] is not None else "N/A",
                monthly_trend=f"{s['monthly_trend']:+.2f}" if s['monthly_trend'] is not None else "N/A",
                research_days=s['days_since_research'] or "unknown",
                open_sessions=s['open_research'],
                news=news_text,
            )
            try:
                resp = await llm.generate(
                    messages=[LLMMessage(role="user", content=prompt)],
                    temperature=0.3, max_tokens=512,
                )
                stock_briefs.append({"ticker": s['ticker'], "name": s['name'], "brief": resp.content})
            except Exception:
                logger.debug("Stock brief LLM call failed for %s (non-critical)", s['ticker'])
                pass

        # 5. Assemble final brief
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
            chg = f" ({s['change_pct']:+.2f}%)" if s['change_pct'] is not None else ""
            trend = f" 月 {s['monthly_trend']:+.2f}%" if s['monthly_trend'] is not None else ""
            research = ""
            if s['days_since_research'] is not None:
                research = f" [研究 {s['days_since_research']}d]"
            news_str = ""
            if s.get("news"):
                news_str = f" 📰 {s['news'][0][:40]}"
            parts.append(f"- {s['ticker']} ({s['name']}): {s['price']:.2f}{chg}{trend}{research}{news_str}")

        brief_content = "\n".join(parts)
        logger.info("Morning brief: %d stocks, %d focus, %d chars",
                     len(stock_data), len(stock_briefs), len(brief_content))

        # 6. Store
        return await _store_brief(session, brief_content, len(stock_data), len(stock_briefs))


async def _store_brief(session, content: str, stocks: int, focus: int) -> dict:
    """Store brief in MorningBrief table and return response."""
    from core.morning_brief import MorningBrief

    brief = MorningBrief(
        content=content,
        char_count=len(content),
        stocks_covered=stocks,
        focus_stocks=focus,
    )
    session.add(brief)
    await session.commit()
    return {
        "status": "ok", "char_count": len(content),
        "stocks_covered": stocks, "focus_stocks": focus,
        "preview": content[:200],
    }
