"""财务数据入库管道 — 用本地 akshare 子进程给 screener 初筛供数。

三层：
- 全市场业绩报表（stock_yjbb_em，一次调用 ~5000 只）→ roe / gross_margin / revenue / net_income
- 单只资产负债表（stock_balance_sheet_by_report_em）→ total_assets / total_liabilities / debt_to_equity / current_ratio
- 单只现金流量表（stock_cash_flow_sheet_by_report_em）→ operating_cash_flow

业绩报表覆盖全市场；bs/cf 逐只拉取较慢，只对初筛候选补采。
"""

from __future__ import annotations

import json
import math
import os
import subprocess

from market.akshare_executor import to_float
from market.domain import FinancialMetricEntry

_MCP_DIR_ENV = "AKSHARE_MCP_DIR"


def _run_child(code: str, timeout: int = 180) -> dict | list | None:
    """本地 akshare venv 子进程执行代码，返回 __R__ JSON payload。"""
    from core.config import settings

    mcp_dir = os.getenv(_MCP_DIR_ENV) or settings.AKSHARE_MCP_DIR
    if not mcp_dir:
        raise RuntimeError(f"{_MCP_DIR_ENV} 未配置")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    result = subprocess.run(
        ["uv", "run", "--directory", mcp_dir, "python", "-c", code],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"akshare 子进程失败: {result.stderr[-300:]}")
    stdout = result.stdout
    if "__R__:" not in stdout:
        return None
    return json.loads(stdout.split("__R__:", 1)[1])


def _num(v) -> float | None:
    f = to_float(v)
    return None if f is None or math.isnan(f) else f


def _fiscal(report_date: str) -> tuple[int, str]:
    """'2024-06-30 00:00:00' → (2024, 'Q2')。"""
    year = int(str(report_date)[:4])
    month = int(str(report_date)[5:7])
    period = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, "Q4")
    return year, period


# 业绩报表列 → 指标键（net_margin 由 net_income/revenue 推算，不在此表）
YJBB_ROW_MAP: dict[str, str] = {
    "roe": "净资产收益率",
    "gross_margin": "销售毛利率",
    "revenue": "营业总收入-营业总收入",
    "net_income": "净利润-净利润",
}


def parse_yjbb_rows(rows: list[dict], fiscal_year: int, fiscal_period: str) -> list[FinancialMetricEntry]:
    """业绩报表行列表 → 指标 entries（缺值跳过；net_margin 可推算时附带）。"""
    entries: list[FinancialMetricEntry] = []
    for row in rows:
        _parse_one_yjbb(row, fiscal_year, fiscal_period, entries)
    return entries


def _parse_one_yjbb(
    row: dict, fiscal_year: int, fiscal_period: str, entries: list[FinancialMetricEntry]
) -> None:
    values: dict[str, float | None] = {}
    for metric, col in YJBB_ROW_MAP.items():
        v = _num(row.get(col))
        values[metric] = v
        if v is not None:
            entries.append(
                FinancialMetricEntry(
                    fiscal_year=fiscal_year, fiscal_period=fiscal_period,
                    metric_name=metric, metric_value=v,
                )
            )
    # 净利率 = 净利润 / 营业总收入 × 100（单位对齐其他百分比指标）
    if values.get("net_income") is not None and values.get("revenue"):
        entries.append(
            FinancialMetricEntry(
                fiscal_year=fiscal_year, fiscal_period=fiscal_period,
                metric_name="net_margin",
                metric_value=values["net_income"] / values["revenue"] * 100,
            )
        )
    return entries


def parse_balance_sheet_row(row: dict) -> list[FinancialMetricEntry]:
    """资产负债表单行（最新期）→ 规模 + 偿债比率 entries。"""
    year, period = _fiscal(row.get("REPORT_DATE", ""))
    entries: list[FinancialMetricEntry] = []

    def _add(metric: str, value: float | None) -> None:
        if value is not None:
            entries.append(
                FinancialMetricEntry(fiscal_year=year, fiscal_period=period, metric_name=metric, metric_value=value)
            )

    total_assets = _num(row.get("TOTAL_ASSETS"))
    total_liab = _num(row.get("TOTAL_LIABILITIES"))
    total_equity = _num(row.get("TOTAL_EQUITY"))
    _add("total_assets", total_assets)
    _add("total_liabilities", total_liab)
    if total_liab is not None and total_equity:
        _add("debt_to_equity", total_liab / total_equity * 100)
    # 银行/保险等 CURRENT_ASSET_BALANCE 恒为 0 → 流动比率无意义，跳过走缺数据路径
    current_asset = _num(row.get("CURRENT_ASSET_BALANCE"))
    current_liab = _num(row.get("CURRENT_LIAB_BALANCE"))
    if current_asset and current_liab:
        _add("current_ratio", current_asset / current_liab)
    return entries


def parse_cash_flow_row(row: dict) -> list[FinancialMetricEntry]:
    """现金流量表单行（最新期）→ operating_cash_flow entry。"""
    year, period = _fiscal(row.get("REPORT_DATE", ""))
    v = _num(row.get("NETCASH_OPERATE"))
    if v is None:
        return []
    return [
        FinancialMetricEntry(fiscal_year=year, fiscal_period=period, metric_name="operating_cash_flow", metric_value=v)
    ]


# ── 拉取层（子进程） ─────────────────────────────────────────────


# akshare 子进程公共头 — 2026-10-22 东财风控三连：
# ① 无浏览器 UA 的请求直接断连 → 打默认 UA
# ② clash 代理对东财域名断连 → NO_PROXY 直连
# ③ 连续分页请求会被掐连接 → urllib3 Retry 自动重试兜底
_AKSHARE_PROLOGUE = (
    "import os\n"
    "os.environ['NO_PROXY'] = '*'\n"
    "for _k in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):\n"
    "    os.environ.pop(_k, None)\n"
    "import socket\n"
    "_orig_gai = socket.getaddrinfo\n"
    "socket.getaddrinfo = lambda *a, **k: [r for r in _orig_gai(*a, **k) if r[0] == socket.AF_INET]\n"
    "import requests\n"
    "from requests.adapters import HTTPAdapter\n"
    "from urllib3.util.retry import Retry\n"
    "_orig_send = HTTPAdapter.send\n"
    "def _send_with_ua(self, request, *a, **k):\n"
    "    request.headers.setdefault('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36')\n"
    "    return _orig_send(self, request, *a, **k)\n"
    "HTTPAdapter.send = _send_with_ua\n"
    "_retry = Retry(total=4, backoff_factor=1.5, status_forcelist=[502, 503, 504], allowed_methods=None)\n"
    "_orig_init = HTTPAdapter.__init__\n"
    "def _init_with_retry(self, *a, **k):\n"
    "    k.setdefault('max_retries', _retry)\n"
    "    return _orig_init(self, *a, **k)\n"
    "HTTPAdapter.__init__ = _init_with_retry\n"
)


async def fetch_yjbb_raw(date: str) -> list[dict]:
    """全市场业绩报表原始行（akshare 子进程，一次调用覆盖 ~5000 只）。

    date 形如 '20240930'（报告期）。
    """
    import asyncio

    code = (
        _AKSHARE_PROLOGUE
        + "import akshare as ak, json\n"
        + f"df = ak.stock_yjbb_em(date={date!r})\n"
        + 'print("__R__:" + json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str))\n'
    )
    return await asyncio.to_thread(_run_child, code, 300)


def _child_single(ticker: str, fn: str) -> dict:
    """单只报表拉取子进程模板（fn: akshare 函数名）。"""
    sec = f"{'SH' if ticker.startswith(('6', '9')) else 'SZ'}{ticker}"
    code = (
        _AKSHARE_PROLOGUE
        + "import akshare as ak, json\n"
        + f"df = ak.{fn}(symbol={sec!r})\n"
        + 'print("__R__:" + json.dumps(df.iloc[0].to_dict(), ensure_ascii=False, default=str))\n'
    )
    out = _run_child(code, 120)
    return out if isinstance(out, dict) else {}


async def fetch_balance_sheet_raw(ticker: str) -> dict:
    """单只最新一期资产负债表原始行。"""
    import asyncio

    return await asyncio.to_thread(_child_single, ticker, "stock_balance_sheet_by_report_em")


async def fetch_cash_flow_raw(ticker: str) -> dict:
    """单只最新一期现金流量表原始行。"""
    import asyncio

    return await asyncio.to_thread(_child_single, ticker, "stock_cash_flow_sheet_by_report_em")


# ── 编排层 ───────────────────────────────────────────────────────


async def ingest_marketwide_yjbb(db, date: str) -> int:
    """全市场业绩报表灌库（roe/gross_margin/revenue/net_income/net_margin）。

    返回成功入库的公司数。单行解析失败跳过该行。
    """
    from core.logging import logger

    raw = await fetch_yjbb_raw(date)
    year, period = _fiscal(f"{date[:4]}-{date[4:6]}-{date[6:8]} 00:00:00")
    ok = 0
    for row in raw:
        ticker = str(row.get("股票代码") or "").strip()
        if len(ticker) != 6 or not ticker.isdigit():
            continue
        try:
            entries = parse_yjbb_rows([row], fiscal_year=year, fiscal_period=period)
            if entries:
                await upsert_metrics(db, ticker, entries)
                ok += 1
        except Exception as e:  # noqa: BLE001 — 单行失败不阻塞全市场
            logger.warning("yjbb 行入库失败 %s: %s", ticker, e)
    logger.info("全市场业绩报表入库: %d/%d 家", ok, len(raw))
    return ok


async def ingest_single_company(db, ticker: str) -> int:
    """单只补采资产负债表 + 现金流量表（初筛候选深判前调用）。

    bs/cf 相互隔离：一边失败不影响另一边。返回写入指标数。
    """
    from core.logging import logger

    total = 0
    for fetch, parse in (
        (fetch_balance_sheet_raw, parse_balance_sheet_row),
        (fetch_cash_flow_raw, parse_cash_flow_row),
    ):
        try:
            raw = await fetch(ticker)
            entries = parse(raw)
            if entries:
                total += await upsert_metrics(db, ticker, entries)
        except Exception as e:  # noqa: BLE001 — bs/cf 隔离
            logger.warning("单只报表拉取失败 %s (%s): %s", ticker, fetch.__name__, e)
    return total


# ── 入库层 ───────────────────────────────────────────────────────

# 指标 → 单位（FinancialMetricUnit 值）
_UNIT_MAP = {
    "roe": "%", "gross_margin": "%", "net_margin": "%",
    "revenue": "元", "net_income": "元", "operating_cash_flow": "元",
    "total_assets": "元", "total_liabilities": "元",
    "debt_to_equity": "%", "current_ratio": "倍",
}


async def upsert_metrics(db, ticker: str, entries: list) -> int:
    """entries → market.financial_metrics（同 ticker 同期同指标幂等覆盖）。

    返回实际写入行数。
    """
    from datetime import datetime

    from sqlalchemy import delete

    from market.models import FinancialMetric

    # 去重（同 metric 只保留最后一条）
    unique: dict[str, FinancialMetricEntry] = {}
    for e in entries:
        unique[e.metric_name] = e

    if not unique:
        return 0

    # 幂等：先删同 ticker 同期同指标旧行
    await db.execute(
        delete(FinancialMetric).where(
            FinancialMetric.ticker == ticker,
            FinancialMetric.fiscal_year == entries[0].fiscal_year,
            FinancialMetric.fiscal_period == entries[0].fiscal_period,
            FinancialMetric.metric_name.in_(list(unique)),
        )
    )

    now = datetime.utcnow()
    for metric, e in unique.items():
        db.add(
            FinancialMetric(
                ticker=ticker,
                fiscal_year=e.fiscal_year,
                fiscal_period=e.fiscal_period,
                metric_name=metric,
                metric_value=e.metric_value,
                metric_unit=_UNIT_MAP.get(metric),
                reported_at=now,
            )
        )
    return len(unique)
