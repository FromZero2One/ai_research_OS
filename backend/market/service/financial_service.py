"""Financial metrics service — query and ingest financial data.

A-stocks → akshare subprocess (stock_yjbb_em 业绩报表)
HK stocks → akshare eastmoney HK API
结果统一入库 PostgreSQL（financial_metrics 表，标准枚举指标名）。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from core.logging import logger
from market.domain import FinancialMetricEntry
from market.repositories import FinancialRepository
from market.service.shared import record_freshness

# HK-stock metric key mapping (Chinese → English)
HK_METRICS = [
    ("营业额", "revenue"),
    ("股东应占溢利", "net_income"),
    ("每股基本盈利", "eps"),
    ("毛利", "gross_profit"),
    ("经营溢利", "operating_profit"),
    ("研发费用", "rd_expense"),
]

_A_FINANCIALS_CODE = """\
import json, os, sys
import akshare as ak
try:
    ticker = os.environ["AKSHARE_TICKER"]
    df = ak.stock_financial_abstract(symbol=ticker)
    if df is None or df.empty:
        print("__R__:[]")
    else:
        rows = []
        period_cols = [c for c in df.columns if str(c).isdigit() and len(str(c)) == 8]
        for _, row in df.iterrows():
            name = str(row.get("指标", "")).strip()
            if not name:
                continue
            for c in period_cols:
                raw = row.get(c)
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    continue
                rows.append({"metric": name, "period": str(c), "value": value})
        print("__R__:" + json.dumps(rows, ensure_ascii=False, default=str))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""

_HK_FINANCIALS_CODE = """\
import json, os, sys
import akshare as ak
try:
    ticker = os.environ["AKSHARE_TICKER"]
    df = ak.stock_financial_hk_report_em(stock=ticker.zfill(5), symbol="利润表", indicator="年度")
    if df is None or df.empty:
        print("__R__:[]")
    else:
        wanted = {"营业额", "股东应占溢利", "每股基本盈利", "毛利", "经营溢利", "研发费用"}
        rows = []
        for cn_name in wanted:
            subset = df[df["STD_ITEM_NAME"] == cn_name]
            for _, row in subset.iterrows():
                rd = row["REPORT_DATE"]
                year = int(str(rd)[:4]) if isinstance(rd, str) else rd.year
                rows.append({"cn": cn_name, "year": year, "value": float(row["AMOUNT"])})
        print("__R__:" + json.dumps(rows, ensure_ascii=False, default=str))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""


class FinancialService:
    """Financial metrics — akshare subprocess with PG cache."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.repo = FinancialRepository(session)

    async def get_financials(
        self,
        ticker: str,
        metric: str | None = None,
        fiscal_year: int | None = None,
    ) -> list[FinancialMetricEntry]:
        """Get financial metrics — PG first, akshare subprocess for misses."""
        ticker_upper = ticker.upper()

        pg_metrics = await self.repo.get_for_ticker(ticker_upper, metric, fiscal_year)
        if pg_metrics:
            return pg_metrics

        try:
            fetched = await self._fetch_akshare_financials(ticker)
            if fetched:
                await self.upsert_financials(ticker, fetched)
                return await self.repo.get_for_ticker(ticker_upper, metric, fiscal_year)
        except Exception:
            logger.warning("Failed to fetch financials from akshare for %s", ticker)
            pass

        return []

    async def upsert_financials(self, ticker: str, metrics: list[FinancialMetricEntry]) -> int:
        """Bulk upsert financial metrics into PostgreSQL."""
        from dataclasses import replace

        from market.models import normalize_metric_name

        normalized = [
            replace(entry, metric_name=normalize_metric_name(entry.metric_name))
            for entry in metrics
        ]
        count = await self.repo.upsert(ticker, normalized)

        if count:
            await self.events.record(
                source="market",
                event_type="financials.ingested",
                entity_type="financial_metric",
                entity_id=ticker,
                payload={"count": count, "ticker": ticker},
            )

        # Record freshness
        await record_freshness(self.session, ticker, "financials", record_count=count, status="ok")

        return count

    async def _fetch_akshare_financials(self, ticker: str) -> list[FinancialMetricEntry]:
        """Fetch financials via the akshare subprocess.

        A-stocks → stock_financial_abstract（财务摘要，多期年度数据）
        HK stocks → eastmoney HK 利润表
        Runs in the isolated akshare_mcp venv — importing akshare into the
        backend process is not possible (not a declared dependency).
        """
        import asyncio as _asyncio

        from market.akshare_executor import build_akshare_env, is_a_stock, run_akshare

        if is_a_stock(ticker):
            code = _A_FINANCIALS_CODE
        else:
            code = _HK_FINANCIALS_CODE

        try:
            stdout = await _asyncio.to_thread(run_akshare, code, build_akshare_env(ticker))
        except Exception:
            return []
        if not stdout:
            return []

        if is_a_stock(ticker):
            return self._parse_a_financials(stdout)
        return self._parse_hk_financials(stdout)

    @staticmethod
    def _period_to_fiscal(period: str) -> tuple[int, str]:
        """YYYYMMDD → (year, fiscal_period)；季报期末日映射 Q1-Q4。"""
        year, md = int(period[:4]), period[4:8]
        quarter = {"0331": "Q1", "0630": "Q2", "0930": "Q3", "1231": "Annual"}.get(md, "Annual")
        return year, quarter

    def _parse_a_financials(self, stdout: str) -> list[FinancialMetricEntry]:
        """解析 A 股财务摘要输出，指标名经 normalize 映射为标准枚举。"""
        import json as _json

        from market.models import normalize_metric_name

        for line in stdout.splitlines():
            if not line.startswith("__R__:"):
                continue
            try:
                rows = _json.loads(line[6:])
            except _json.JSONDecodeError:
                return []
            results: list[FinancialMetricEntry] = []
            for r in rows:
                year, fp = self._period_to_fiscal(str(r["period"]))
                results.append(
                    FinancialMetricEntry(
                        fiscal_year=year,
                        fiscal_period=fp,
                        metric_name=normalize_metric_name(str(r["metric"])),
                        metric_value=float(r["value"]),
                    )
                )
            return results
        return []

    def _parse_hk_financials(self, stdout: str) -> list[FinancialMetricEntry]:
        """解析港股利润表输出（中文指标 → 英文枚举）。"""
        import json as _json

        name_to_en = dict(HK_METRICS)
        results: list[FinancialMetricEntry] = []
        for line in stdout.splitlines():
            if not line.startswith("__R__:"):
                continue
            try:
                rows = _json.loads(line[6:])
            except _json.JSONDecodeError:
                return []
            for r in rows:
                en_name = name_to_en.get(r.get("cn"))
                if en_name is None:
                    continue
                results.append(
                    FinancialMetricEntry(
                        fiscal_year=int(r["year"]),
                        fiscal_period="Annual",
                        metric_name=en_name,
                        metric_value=float(r["value"]),
                    )
                )
            break
        return results
