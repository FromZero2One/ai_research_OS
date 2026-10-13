"""Stock search service — PG Companies 表检索（用户的研究宇宙）。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class SearchService:
    """Search stocks by code/name in the PostgreSQL Companies table.

    搜索范围即用户已录入的公司（A/HK/US）。全市场股票列表检索随
    akshare MySQL 镜像层一并移除——个人研究工具的搜索对象是自建公司库。
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search_stocks(self, query: str, limit: int = 20) -> list[dict]:
        """Search companies by code or name."""
        from company.models import Company

        stmt = (
            select(Company)
            .where((Company.ticker.ilike(f"%{query}%")) | (Company.name.ilike(f"%{query}%")))
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return [{"symbol": c.ticker, "name": c.name} for c in rows.scalars().all()]
