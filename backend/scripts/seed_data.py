# ruff: noqa: E501
"""Seed sample A-share companies for development."""

from __future__ import annotations

import asyncio

from core.database import async_session_factory, engine
from core.logging import configure_logging, logger

SAMPLE_COMPANIES = [
    {
        "ticker": "600519",
        "name": "贵州茅台",
        "sector": "Consumer Staples",
        "industry": "白酒",
        "description": "贵州茅台酒股份有限公司，主营茅台酒及系列酒的生产与销售。",
    },
    {
        "ticker": "000002",
        "name": "万科A",
        "sector": "Real Estate",
        "industry": "房地产开发",
        "description": "万科企业股份有限公司，主营房地产开发与物业服务。",
    },
    {
        "ticker": "300750",
        "name": "宁德时代",
        "sector": "Technology",
        "industry": "电池",
        "description": "宁德时代新能源科技股份有限公司，全球领先的动力电池与储能系统提供商。",
    },
    {
        "ticker": "601398",
        "name": "工商银行",
        "sector": "Financials",
        "industry": "银行",
        "description": "中国工商银行股份有限公司，大型国有商业银行。",
    },
]


async def seed() -> None:
    """Insert sample companies."""
    configure_logging()
    logger.info("Seeding sample data...")

    async with async_session_factory() as session:
        from company.models import Company

        created = 0
        for data in SAMPLE_COMPANIES:
            try:
                session.add(Company(**data, is_active=True))
                logger.info("  Created: %s (%s)", data["ticker"], data["name"])
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
