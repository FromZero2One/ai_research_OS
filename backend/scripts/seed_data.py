# ruff: noqa: E501
"""Seed sample companies and a research session for development."""

from __future__ import annotations

import asyncio

from core.database import async_session_factory, engine
from core.logging import configure_logging, logger

SAMPLE_COMPANIES = [
    {
        "ticker": "AAPL",
        "name": "Apple Inc.",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "description": "Apple designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories.",
        "headquarters": "Cupertino, CA",
        "founded_year": 1976,
        "employees": 164000,
        "website": "https://apple.com",
        "tags": ["tech", "consumer", "hardware", "megacap"],
    },
    {
        "ticker": "MSFT",
        "name": "Microsoft Corporation",
        "sector": "Technology",
        "industry": "Software—Infrastructure",
        "description": "Microsoft develops and supports software, services, devices, and solutions worldwide.",
        "headquarters": "Redmond, WA",
        "founded_year": 1975,
        "employees": 228000,
        "website": "https://microsoft.com",
        "tags": ["tech", "software", "cloud", "ai", "megacap"],
    },
    {
        "ticker": "GOOGL",
        "name": "Alphabet Inc.",
        "sector": "Technology",
        "industry": "Internet Content & Information",
        "description": "Alphabet provides online advertising services, search engine, cloud solutions, and other products.",
        "headquarters": "Mountain View, CA",
        "founded_year": 1998,
        "employees": 190000,
        "website": "https://abc.xyz",
        "tags": ["tech", "search", "cloud", "ai", "megacap"],
    },
    {
        "ticker": "AMZN",
        "name": "Amazon.com Inc.",
        "sector": "Technology",
        "industry": "Internet Retail",
        "description": "Amazon engages in retail, e-commerce, cloud computing, digital streaming, and artificial intelligence.",
        "headquarters": "Seattle, WA",
        "founded_year": 1994,
        "employees": 1540000,
        "website": "https://amazon.com",
        "tags": ["tech", "ecommerce", "cloud", "megacap"],
    },
    {
        "ticker": "NVDA",
        "name": "NVIDIA Corporation",
        "sector": "Technology",
        "industry": "Semiconductors",
        "description": "NVIDIA designs graphics processing units and chips for gaming, professional visualization, data centers, and AI.",
        "headquarters": "Santa Clara, CA",
        "founded_year": 1993,
        "employees": 32000,
        "website": "https://nvidia.com",
        "tags": ["tech", "semiconductor", "ai", "gpu"],
    },
    {
        "ticker": "TSLA",
        "name": "Tesla Inc.",
        "sector": "Consumer Cyclical",
        "industry": "Auto Manufacturers",
        "description": "Tesla designs, develops, manufactures, and sells electric vehicles and energy generation/storage systems.",
        "headquarters": "Austin, TX",
        "founded_year": 2003,
        "employees": 140000,
        "website": "https://tesla.com",
        "tags": ["ev", "automotive", "energy", "innovation"],
    },
    {
        "ticker": "JPM",
        "name": "JPMorgan Chase & Co.",
        "sector": "Financial Services",
        "industry": "Banks—Diversified",
        "description": "JPMorgan Chase is a global financial services firm providing investment banking, financial services, and asset management.",
        "headquarters": "New York, NY",
        "founded_year": 1799,
        "employees": 293000,
        "website": "https://jpmorganchase.com",
        "tags": ["finance", "banking", "megacap"],
    },
    {
        "ticker": "BRK.B",
        "name": "Berkshire Hathaway Inc.",
        "sector": "Financial Services",
        "industry": "Insurance—Diversified",
        "description": "Berkshire Hathaway is a conglomerate holding company owning subsidiaries in insurance, railroads, utilities, and manufacturing.",
        "headquarters": "Omaha, NE",
        "founded_year": 1839,
        "employees": 372000,
        "website": "https://berkshirehathaway.com",
        "tags": ["conglomerate", "value", "warren-buffett"],
    },
]


async def seed() -> None:
    """Insert sample companies."""
    configure_logging()
    logger.info("Seeding sample data...")

    async with async_session_factory() as session:
        # Create companies
        from company.service import CompanyService

        svc = CompanyService(session)
        created = 0
        for data in SAMPLE_COMPANIES:
            tags = data.pop("tags", [])
            try:
                company = await svc.create(**data, tags=tags)
                logger.info("  Created: %s (%s)", company.ticker, company.name)
                created += 1
            except Exception as e:
                logger.warning("  Skip %s: %s", data["ticker"], e)

        await session.commit()
        logger.info("Seeding complete: %d companies", created)


async def init_db() -> None:
    """Create all tables (fresh database)."""
    configure_logging()
    from core.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("All tables created")


async def main() -> None:
    await init_db()
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
