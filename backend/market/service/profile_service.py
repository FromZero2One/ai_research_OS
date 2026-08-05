"""Company profile and stock info service — powers company detail views."""

from __future__ import annotations

from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter
from core.event_service import EventLogger
from core.logging import logger
from market.akshare_executor import is_a_stock

_PROFILE_CODE = """\
import json, os, sys
import akshare as ak
try:
    ticker = os.environ["AKSHARE_TICKER"]
    if len(ticker) in (4, 5):
        df = ak.stock_hk_company_profile_em(symbol=ticker.zfill(5))
        if df is None or df.empty:
            print("__R__:{}")
        else:
            row = df.iloc[0]
            emp_raw = row.get("员工人数")
            try:
                employees = int(emp_raw)
            except (ValueError, TypeError):
                employees = None
            print("__R__:" + json.dumps({
                "name": str(row.get("公司名称", "")),
                "sector": row.get("所属行业"),
                "industry": row.get("所属行业"),
                "description": str(row.get("公司介绍", ""))[:2000] if row.get("公司介绍") else None,
                "website": row.get("公司网址"),
                "headquarters": row.get("办公地址"),
                "founded_year": (
                    int(str(row.get("公司成立日期", ""))[:4])
                    if row.get("公司成立日期") else None
                ),
                "employees": employees,
            }, ensure_ascii=False, default=str))
    else:
        df = ak.stock_profile_cninfo(symbol=ticker)
        if df is None or df.empty:
            print("__R__:{}")
        else:
            row = df.iloc[0]
            print("__R__:" + json.dumps({
                "name": str(row.get("公司名称", "")),
                "sector": row.get("所属行业"),
                "industry": row.get("所属行业"),
                "description": str(row.get("机构简介", ""))[:2000] if row.get("机构简介") else None,
                "website": row.get("官方网站"),
                "headquarters": row.get("办公地址"),
                "founded_year": (
                    int(str(row.get("成立日期", ""))[:4])
                    if row.get("成立日期") else None
                ),
            }, ensure_ascii=False, default=str))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""


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
        """Get stock name, sector and kline status."""
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
        """Fetch company profile via the akshare subprocess and update the Company row in PG.

        Runs akshare in the isolated akshare_mcp venv (ticker passed via env var)
        instead of importing akshare into the backend process, which is not a
        declared dependency and would fail with ModuleNotFoundError.
        """
        import asyncio as _asyncio
        import json as _json

        from company.models import Company
        from market.akshare_executor import build_akshare_env, run_akshare

        profile: dict[str, str | int | None] = {}
        try:
            stdout = await _asyncio.to_thread(run_akshare, _PROFILE_CODE, build_akshare_env(ticker))
            if stdout:
                for line in stdout.splitlines():
                    if line.startswith("__R__:"):
                        profile = _json.loads(line[6:])
                        break
        except (_json.JSONDecodeError, ValueError) as e:
            logger.warning("  [profile] fetch failed for %s: %s", ticker, e)
            return {}

        if not profile:
            return profile

        update_data = {k: v for k, v in profile.items() if v is not None}
        if update_data:
            stmt = sql_update(Company).where(Company.ticker == ticker).values(**update_data)
            await self.session.execute(stmt)
            await self.session.flush()
            await self.events.record(
                source="market",
                event_type="company_profile.ingested",
                entity_type="company",
                entity_id=ticker,
                payload=update_data,
            )
            logger.info("  [profile] updated %s: %s", ticker, list(update_data.keys()))

        # Record freshness (even if no profile data, the fetch was attempted)
        from market.service.freshness_service import FreshnessService

        freshness = FreshnessService(self.session)
        count = len(update_data) if update_data else 0
        status = "ok" if profile else "error"
        await freshness.record_fetch(
            ticker,
            "profile",
            record_count=count,
            status=status,
            error_message=None if profile else "No profile data returned",
        )

        return profile
