"""News fetching helpers for scheduled jobs (newsnow MCP + akshare)."""

from __future__ import annotations

from core.logging import logger


async def fetch_newsnow(sectors: list[str] | None = None) -> list[str]:
    """Fetch financial news relevant to given sectors via persistent MCP."""
    from core.adapters.newsnow_mcp import get_headlines

    return await get_headlines(sectors=sectors)


async def fetch_news_akshare(ticker: str) -> list[dict]:
    """Fetch stock news via the akshare subprocess (ticker passed via env).

    Single source of truth: ``NewsService.fetch_news`` owns the subprocess
    code; this module is a thin scheduled-job-friendly wrapper.
    """
    from market.service.news_service import NewsService

    try:
        news, _source = await NewsService().fetch_news(ticker)
        return news
    except Exception:
        logger.debug("akshare news subprocess failed")
        return []
