"""Company service — read-only search (CRUD/thesis retired, table stays).

Company 表仍被 screener 数据质量统计、market search/freshness、
document.company_id 外键消费；本服务只保留文档中心关联下拉用的检索。
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company


class CompanyService:
    """Read-only company lookup."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search(
        self,
        query: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Company], int]:
        """Search companies by name/ticker (document association picker)."""
        stmt = select(Company)

        if query:
            stmt = stmt.where(Company.name.ilike(f"%{query}%") | Company.ticker.ilike(f"%{query}%"))

        count_stmt = stmt.with_only_columns(func.count(Company.id)).order_by(None)
        total = (await self.session.execute(count_stmt)).scalar() or 0

        stmt = stmt.offset(skip).limit(limit).order_by(Company.ticker)
        result = await self.session.execute(stmt)
        companies = list(result.scalars().all())

        return companies, total
