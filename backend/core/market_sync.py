"""Scheduled job: daily market data synchronization."""

from __future__ import annotations

from sqlalchemy import select

from company.models import Company
from core.container import create_container
from core.database import managed_session
from core.logging import logger


async def market_data_update() -> dict:
    """Daily: Pull latest market data for all tracked companies.

    For A-stocks: sync from akshare MySQL.
    For US stocks: data is already seeded; this is a placeholder for
    a future yfinance/API integration.
    """
    async with managed_session() as session:
        market = create_container(session).price_service

        result = await session.execute(select(Company.ticker).where(Company.is_active.is_(True)))
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
