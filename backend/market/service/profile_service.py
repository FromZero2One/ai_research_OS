"""Company profile and stock info service — powers company detail views."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

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
    """Company profile, stock info, and valuation — PG + akshare subprocess."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    async def get_stock_info(self, ticker: str) -> dict | None:
        """Get stock basic info + latest valuation (A-stocks only).

        名称/最新价取自 PG（公司表 + 价格缓存），估值（PE/PB/总市值）
        经 akshare 直连取乐咕乐股每日指标，不落库只透出。
        """
        if not is_a_stock(ticker):
            return None

        from company.models import Company
        from market.repositories import PriceRepository

        company = (
            await self.session.execute(select(Company).where(Company.ticker == ticker))
        ).scalar_one_or_none()
        name = company.name if company else None
        latest = await PriceRepository(self.session).get_for_ticker(ticker, limit=1)
        latest_price = latest[0].close if latest else None

        return {
            "ticker": ticker,
            "name": name,
            "latest_price": latest_price,
            "valuation": await self._fetch_valuation(ticker),
            "source": "pg+akshare",
        }

    async def _fetch_valuation(self, ticker: str) -> dict | None:
        """A 股估值指标（PE/PB/总市值）—— akshare stock_a_indicator_lg 直连。"""
        import asyncio as _asyncio
        import json as _json

        from market.akshare_executor import build_akshare_env, run_akshare

        code = (
            "import json, os, sys\nimport akshare as ak\n"
            "def _g(row, k):\n"
            "    v = row.get(k)\n"
            "    return float(v) if v is not None and v == v else None\n"
            "try:\n"
            '    ticker = os.environ["AKSHARE_TICKER"]\n'
            "    df = ak.stock_a_indicator_lg(symbol=ticker)\n"
            '    if df is None or df.empty:\n        print("__R__:{}")\n'
            "    else:\n"
            "        row = df.iloc[-1]\n"
            "        print(\"__R__:\" + json.dumps({\n"
            '            "pe": _g(row, "pe"), "pe_ttm": _g(row, "pe_ttm"),\n'
            '            "pb": _g(row, "pb"), "total_mv": _g(row, "total_mv"),\n'
            '            "dv_ttm": _g(row, "dv_ttm"),\n'
            "        }))\n"
            "except Exception as e:\n"
            '    print("__E__:" + str(e), file=sys.stderr)\n'
        )
        try:
            stdout = await _asyncio.to_thread(run_akshare, code, build_akshare_env(ticker))
        except Exception as e:
            logger.warning("  [valuation] fetch failed for %s: %s", ticker, e)
            return None
        for line in stdout.splitlines():
            if line.startswith("__R__:"):
                try:
                    data = _json.loads(line[6:])
                except _json.JSONDecodeError:
                    return None
                return data or None
        return None

    async def get_stock_profile(self, ticker: str) -> dict | None:
        """Get stock name/sector/kline status from PG (company row + price cache)."""
        from company.models import Company
        from market.repositories import PriceRepository

        result = await self.session.execute(
            select(Company).where(Company.ticker == ticker)
        )
        company = result.scalar_one_or_none()
        if not company:
            return None

        has_kline = bool(
            await PriceRepository(self.session).get_for_ticker(ticker, limit=1)
        )

        tags = []
        if company.industry:
            clean = company.industry.replace("Ⅱ", "").replace("Ⅰ", "")
            tags.append(clean[:10])
        if has_kline:
            tags.append("kline")

        return {
            "symbol": ticker,
            "name": company.name,
            "sector": company.industry,
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
