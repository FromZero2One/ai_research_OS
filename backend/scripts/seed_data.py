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
        "tags": ["消费", "白酒", "龙头"],
    },
    {
        "ticker": "000002",
        "name": "万科A",
        "sector": "Real Estate",
        "industry": "房地产开发",
        "description": "万科企业股份有限公司，主营房地产开发与物业服务。",
        "tags": ["地产", "龙头"],
    },
    {
        "ticker": "300750",
        "name": "宁德时代",
        "sector": "Technology",
        "industry": "电池",
        "description": "宁德时代新能源科技股份有限公司，全球领先的动力电池与储能系统提供商。",
        "tags": ["新能源", "电池", "龙头"],
    },
    {
        "ticker": "601398",
        "name": "工商银行",
        "sector": "Financials",
        "industry": "银行",
        "description": "中国工商银行股份有限公司，大型国有商业银行。",
        "tags": ["金融", "银行", "高股息"],
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
