"""Company profile and stock info service — for mcp-company and company detail views."""

from __future__ import annotations

from sqlalchemy import select, update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter
from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import is_a_stock


class ProfileService:
    """Company profile, stock info, and valuation — sourced from akshare MySQL + API."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self._mysql: AkshareMySQLAdapter | None = None

    async def _get_mysql(self) -> AkshareMySQLAdapter:
        if self._mysql is None:
            self._mysql = AkshareMySQLAdapter()
        return self._mysql

    async def get_stock_info(self, ticker: str) -> dict | None:
        """Get stock basic info + latest valuation (A-stocks only)."""
        if not is_a_stock(ticker):
            return None

        mysql = await self._get_mysql()
        name = await mysql.get_name(ticker)
        valuation = await mysql.get_valuation(ticker)
        prices = await mysql.get_prices(ticker, limit=1)
        latest_price = prices[0].close if prices else None

        return {
            "ticker": ticker,
            "name": name,
            "latest_price": latest_price,
            "valuation": valuation,
            "source": "akshare_mysql",
        }

    async def get_stock_profile(self, ticker: str) -> dict | None:
        """Get stock name, sector and kline status — used by mcp-company."""
        if not is_a_stock(ticker):
            return None

        mysql = await self._get_mysql()
        name = await mysql.get_name(ticker)
        if not name:
            return None

        sector = await mysql.get_sector(ticker)
        has_kline = await mysql.has_kline(ticker)

        tags = []
        if sector:
            clean = sector.replace("Ⅱ", "").replace("Ⅰ", "")
            tags.append(clean[:10])
        if has_kline:
            tags.append("kline")

        return {
            "symbol": ticker,
            "name": name,
            "sector": sector,
            "has_kline": has_kline,
            "tags": tags,
        }

    async def fetch_and_store_company_profile(self, ticker: str) -> dict:
        """Fetch company profile data via akshare and update the Company record in PG."""
        import akshare as ak
        import asyncio as _asyncio
        from company.models import Company

        profile: dict[str, str | int | None] = {}
        is_hk = ticker.strip().isdigit() and len(ticker.strip()) in (4, 5)

        def _fetch_a():
            df = ak.stock_profile_cninfo(symbol=ticker)
            if df is None or df.empty:
                return {}
            row = df.iloc[0]
            cn_name = str(row.get("公司名称", ""))
            return {
                "name": cn_name if cn_name else None,
                "sector": row.get("所属行业"),
                "industry": row.get("所属行业"),
                "description": str(row.get("机构简介", ""))[:2000] if row.get("机构简介") else None,
                "website": row.get("官方网站"),
                "headquarters": row.get("办公地址"),
                "founded_year": int(str(row.get("成立日期", ""))[:4]) if row.get("成立日期") else None,
            }

        def _fetch_hk():
            hk_sym = ticker.zfill(5)
            df = ak.stock_hk_company_profile_em(symbol=hk_sym)
            if df is None or df.empty:
                return {}
            row = df.iloc[0]
            emp_raw = row.get("员工人数")
            try:
                employees = int(emp_raw)
            except (ValueError, TypeError):
                employees = None
            hk_name = str(row.get("公司名称", ""))
            return {
                "name": hk_name if hk_name else None,
                "sector": row.get("所属行业"),
                "industry": row.get("所属行业"),
                "description": str(row.get("公司介绍", ""))[:2000] if row.get("公司介绍") else None,
                "website": row.get("公司网址"),
                "headquarters": row.get("办公地址"),
                "founded_year": int(str(row.get("公司成立日期", ""))[:4]) if row.get("公司成立日期") else None,
                "employees": employees,
            }

        try:
            profile = await _asyncio.to_thread(_fetch_hk if is_hk else _fetch_a)
        except Exception as e:
            logger.warning("  [profile] fetch failed for %s: %s", ticker, e)
            return {}

        if not profile:
            return profile

        update_data = {k: v for k, v in profile.items() if v is not None}
        if update_data:
            stmt = (
                sql_update(Company)
                .where(Company.ticker == ticker)
                .values(**update_data)
            )
            await self.session.execute(stmt)
            await self.session.flush()
            await self.events.record(
                source="market", event_type="company_profile.ingested",
                entity_type="company", entity_id=ticker,
                payload=update_data,
            )
            logger.info("  [profile] updated %s: %s", ticker, list(update_data.keys()))

        # Record freshness (even if no profile data, the fetch was attempted)
        from market.freshness_service import FreshnessService
        freshness = FreshnessService(self.session)
        count = len(update_data) if update_data else 0
        status = "ok" if profile else "error"
        await freshness.record_fetch(
            ticker, "profile",
            record_count=count, status=status,
            error_message=None if profile else "No profile data returned",
        )

        return profile
