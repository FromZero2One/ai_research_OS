"""比率层 — 财务比率派生 + A 股 PE/PB 历史分位。

纯函数（compute_ratios / percentile_rank / build_percentile_result）可独立单测；
RatioService 负责取数与缓存（PG first，akshare 子进程兜底）。
数字唯一事实源原则：原料只来自 market.financial_metrics / market.valuation_history，
不从文档/证据抽数。
"""

from __future__ import annotations

from datetime import date as _date

from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from market import akshare_executor
from market.domain import FinancialMetricEntry
from market.repositories import FinancialRepository, ValuationRepository

# 比率键 → 中文标签（报告区块与前端共用）
RATIO_LABELS: dict[str, str] = {
    "gross_margin": "毛利率",
    "net_margin": "净利率",
    "roe": "ROE",
    "debt_to_equity": "资产负债率",
    "asset_turnover": "总资产周转率",
    "inventory_turnover": "存货周转率",
    "receivables_turnover": "应收账款周转率",
    "current_ratio": "流动比率",
    "quick_ratio": "速动比率",
    "eps": "每股收益",
    "market_cap": "总市值",
}

_PERIOD_RANK = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Annual": 5}

# 透出类比率（financial_metrics 已有原始值，直接带出）
_PASSTHROUGH = (
    "roe", "debt_to_equity", "asset_turnover", "inventory_turnover",
    "receivables_turnover", "current_ratio", "quick_ratio", "eps", "market_cap",
)


def _metric_lookup(
    metrics: list[FinancialMetricEntry],
) -> dict[tuple[int, str], dict[str, float]]:
    """按 (年度, 报告期) 分组取第一个非空值（先到先得）。"""
    grouped: dict[tuple[int, str], dict[str, float]] = {}
    for m in metrics:
        if m.metric_value is None:
            continue
        grouped.setdefault((m.fiscal_year, m.fiscal_period), {}).setdefault(
            m.metric_name, m.metric_value
        )
    return grouped


def _dedup_periods(periods: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """同年并存 Annual 时丢弃 Q4（年报即 Q4 期末，口径重复）；Q1-Q3 保留为中期数据。"""
    annual_years = {y for y, p in periods if p == "Annual"}
    return [
        (y, p) for y, p in periods
        if p == "Annual" or p != "Q4" or y not in annual_years
    ]


def compute_ratios(metrics: list[FinancialMetricEntry]) -> list[dict]:
    """由财务指标派生比率；缺原料或除零 → None，不猜测。按报告期倒序返回全部期。"""
    grouped = _metric_lookup(metrics)
    periods = _dedup_periods(list(grouped))
    periods.sort(key=lambda p: (p[0], _PERIOD_RANK.get(p[1], 0)), reverse=True)

    out: list[dict] = []
    for year, period in periods:
        vals = grouped[(year, period)]
        revenue = vals.get("revenue")

        def _margin(numer: float | None) -> float | None:
            if numer is None or not revenue:
                return None
            return round(numer / revenue * 100, 4)

        row: dict = {
            "fiscal_year": year,
            "fiscal_period": period,
            "gross_margin": _margin(vals.get("gross_profit")),
            "net_margin": _margin(vals.get("net_income")),
        }
        row.update({k: vals.get(k) for k in _PASSTHROUGH})
        out.append(row)
    return out


def percentile_rank(series: list[float], value: float | None) -> float | None:
    """value 在序列中的百分位（<= value 的比例 × 100）。

    空序列或 value 为 None → None；单一值 → 50（无分布意义，取中性）。
    """
    if value is None or not series:
        return None
    if len(series) == 1:
        return 50.0
    return round(sum(1 for x in series if x <= value) / len(series) * 100, 1)


def build_percentile_result(ticker: str, rows) -> dict:
    """由估值历史序列（按 trade_date 升序）构建分位结果（纯函数）。

    rows 为含 trade_date/pe/pe_ttm/pb 属性的对象序列（ORM 行）。
    current 取最新交易日的值。
    """
    if not rows:
        return {"ticker": ticker, "available": False, "reason": "no_data"}
    latest = rows[-1]
    fields: dict[str, dict] = {}
    for field in ("pe", "pe_ttm", "pb"):
        series = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        current = getattr(latest, field)
        fields[field] = {
            "current": current,
            "percentile": percentile_rank(series, current),
            "samples": len(series),
        }
    return {
        "ticker": ticker,
        "available": True,
        "trade_date": latest.trade_date.isoformat(),
        "start_date": rows[0].trade_date.isoformat(),
        **fields,
    }


# A 股估值历史全序列（乐咕乐股），ticker 经环境变量传入
_A_VALUATION_HISTORY_CODE = """\
import json, os, sys
import akshare as ak
try:
    ticker = os.environ["AKSHARE_TICKER"]
    df = ak.stock_a_indicator_lg(symbol=ticker)
    if df is None or df.empty:
        print("__R__:[]")
    else:
        def _g(row, k):
            v = row.get(k)
            return float(v) if v is not None and v == v else None
        rows = []
        for _, row in df.iterrows():
            rows.append({
                "trade_date": str(row.get("trade_date"))[:10],
                "pe": _g(row, "pe"), "pe_ttm": _g(row, "pe_ttm"),
                "pb": _g(row, "pb"), "total_mv": _g(row, "total_mv"),
            })
        print("__R__:" + json.dumps(rows, ensure_ascii=False))
except Exception as e:
    print("__E__:" + str(e), file=sys.stderr)
"""


class RatioService:
    """比率层服务 — 财务比率（PG）+ A 股 PE/PB 历史分位（PG first，akshare 兜底）。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)
        self.financial_repo = FinancialRepository(session)
        self.valuation_repo = ValuationRepository(session)

    async def read_ratios(self, ticker: str, limit: int = 3) -> list[dict]:
        """最近 N 期财务比率（纯函数计算，原料只来自指标库）。"""
        metrics = await self.financial_repo.get_for_ticker(ticker.upper())
        return compute_ratios(metrics)[:limit]

    async def valuation_percentile(self, ticker: str) -> dict:
        """PE/PE-TTM/PB 历史分位（仅 A 股）。历史不足 2 行时先经 akshare 拉全量入库。"""
        ticker_upper = ticker.upper()
        if not akshare_executor.is_a_stock(ticker):
            return {"ticker": ticker_upper, "available": False, "reason": "non_a_stock"}
        rows = await self.valuation_repo.get_for_ticker(ticker_upper)
        if len(rows) < 2:
            fetched = await self._fetch_valuation_history(ticker_upper)
            if fetched:
                await self.valuation_repo.upsert(ticker_upper, fetched)
                await self.events.record(
                    source="market",
                    event_type="valuation_history.ingested",
                    entity_type="valuation_history",
                    entity_id=ticker_upper,
                    payload={"count": len(fetched), "ticker": ticker_upper},
                )
                rows = await self.valuation_repo.get_for_ticker(ticker_upper)
        return build_percentile_result(ticker_upper, rows)

    async def _fetch_valuation_history(self, ticker: str) -> list[dict]:
        """akshare 子进程拉估值历史；失败返回 []（不抛错，分位退化为无数据）。

        注意：经模块引用调用 run_akshare，保证 monkeypatch 模块属性时可生效。
        """
        import asyncio as _asyncio
        import json as _json

        try:
            stdout = await _asyncio.to_thread(
                akshare_executor.run_akshare,
                _A_VALUATION_HISTORY_CODE,
                akshare_executor.build_akshare_env(ticker),
            )
        except Exception:
            return []
        if not stdout:
            return []
        for line in stdout.splitlines():
            if not line.startswith("__R__:"):
                continue
            try:
                raw = _json.loads(line[6:])
            except _json.JSONDecodeError:
                return []
            rows: list[dict] = []
            for r in raw:
                try:
                    trade_date = _date.fromisoformat(str(r.get("trade_date", ""))[:10])
                except ValueError:
                    continue
                rows.append(
                    {
                        "trade_date": trade_date,
                        "pe": r.get("pe"),
                        "pe_ttm": r.get("pe_ttm"),
                        "pb": r.get("pb"),
                        "total_mv": r.get("total_mv"),
                    }
                )
            return rows
        return []
