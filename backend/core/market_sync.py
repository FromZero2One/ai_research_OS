"""Scheduled job: daily market data synchronization."""

from __future__ import annotations

from sqlalchemy import select

from company.models import Company
from core.container import create_container
from core.database import managed_session
from core.logging import logger


async def market_data_update() -> dict:
    """Daily: pull the latest prices for tracked companies into PostgreSQL.

    A-stocks (6 digits) sync from the akshare MySQL mirror (Layer 1); HK stocks
    (4-5 digits) use the local akshare subprocess. US stocks have no akshare
    source and are left as-is (seeded data).

    Previously this job only called ``get_prices``, which reads the PostgreSQL
    cache and only reaches the upstream sources when the cache is empty — so
    existing rows were never refreshed. Now it fetches and stores every syncable
    ticker, then records freshness (success or error) for the dashboard.
    """
    async with managed_session() as session:
        container = create_container(session)
        price_svc = container.price_service

        result = await session.execute(select(Company.ticker).where(Company.is_active.is_(True)))
        tickers = [row[0] for row in result.all()]
        # A-stocks (6 digits) + HK stocks (4-5 digits) have an akshare source.
        syncable = [t for t in tickers if t.strip().isdigit()]
        logger.info("Market data update: %d syncable tickers", len(syncable))

        updated = 0
        for ticker in syncable:
            try:
                count, warns = await price_svc.fetch_and_store_prices(ticker)
                if count:
                    updated += 1
                elif warns:
                    freshness = container.freshness_service
                    await freshness.record_fetch(
                        ticker,
                        "prices",
                        record_count=0,
                        status="error",
                        error_message="; ".join(warns)[:500],
                    )
            except Exception as e:
                logger.debug("Skipping %s: %s", ticker, e)

        logger.info("Market data update: %d/%d tickers updated", updated, len(syncable))
        return {"tickers_checked": len(syncable), "updated": updated}
