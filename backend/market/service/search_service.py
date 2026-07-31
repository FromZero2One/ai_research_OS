"""Stock search and symbol listing service."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter
from core.logging import logger


class SearchService:
    """Search stocks by code/name across PG (all) and MySQL (A-stocks)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._mysql: AkshareMySQLAdapter | None = None

    async def _get_mysql(self) -> AkshareMySQLAdapter:
        if self._mysql is None:
            self._mysql = AkshareMySQLAdapter()
        return self._mysql

    async def search_stocks(self, query: str, limit: int = 20) -> list[dict]:
        """Search stocks by code or name — MySQL (A-stocks) + PostgreSQL (all)."""
        results: list[dict] = []
        seen = set()

        # PostgreSQL: search Companies table (A, HK, US stocks)
        from company.models import Company
        stmt = select(Company).where(
            (Company.ticker.ilike(f"%{query}%"))
            | (Company.name.ilike(f"%{query}%"))
        ).limit(limit)
        rows = await self.session.execute(stmt)
        for c in rows.scalars().all():
            key = c.ticker.upper()
            if key not in seen:
                seen.add(key)
                results.append({"symbol": c.ticker, "name": c.name})

        # MySQL: search akshare stock_name_entity
        try:
            mysql = await self._get_mysql()
            mysql_results = await mysql.search_stocks(query, limit)
            for r in mysql_results:
                key = r.get("symbol", "").upper()
                if key not in seen:
                    seen.add(key)
                    results.append(r)
        except Exception:
            logger.warning("Failed to search stocks in MySQL")
            pass

        return results[:limit]

    async def list_available_symbols(self, limit: int = 100) -> list[dict]:
        """List all A-stocks with K-line data available."""
        mysql = await self._get_mysql()
        symbols = await mysql.list_symbols(limit)
        result = []
        for sym in symbols:
            name = await mysql.get_name(sym)
            result.append({"symbol": sym, "name": name})
        return result
