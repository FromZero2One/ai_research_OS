"""回测数据准备 — 外部 MySQL 前复权日线 + 历史财务按期补拉 + 基准指数。

数据守则（spec 2026-10-23）：
- 外部库全部 qfq，close 直接用于收益计算（除权已处理）
- 外部库有同票同日重复行 → 拉取侧去重
- 本地灌库幂等（先删同 ticker 日期范围再插）
- 历史财务按报告期调 ingest 的市场级拉取（SAVEPOINT 隔离单期失败）
- 外部 MySQL 凭据仅存 settings.BACKTEST_MYSQL_URL；to_thread + connect_timeout
"""

from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger

# 报告期 → (报告期截止日字符串, 披露完成截止日)
_PERIOD_END = {"Q1": "0331", "Q2": "0630", "Q3": "0930", "Q4": "1231"}


def _period_from_date_str(date_str: str) -> str:
    """'20240930' → 'Q3'（按报告期截止月日映射）。"""
    md = date_str[4:8]
    return {"0331": "Q1", "0630": "Q2", "0930": "Q3", "1231": "Q4"}.get(md, "Q4")


def _period_date_str(year: int, period: str) -> str:
    return f"{year}{_PERIOD_END[period]}"


# ── 外部 MySQL 日线 ──────────────────────────────────────────────


def _fetch_daily_sync(url: str, tickers: list[str], start: dt.date, end: dt.date) -> list[tuple]:
    """同步拉取（线程池中执行）。SELECT 侧按日期范围过滤；重复行留待上层去重。"""
    import pymysql

    conn = pymysql.connect(
        host=_parse_host(url), user=_parse_user(url), password=_parse_password(url),
        database=_parse_db(url), port=_parse_port(url), connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(tickers))
            cur.execute(
                "SELECT symbol, date, open, close, high, low, volume "
                f"FROM akshare.stock_history_daily_info_entity "
                f"WHERE symbol IN ({placeholders}) AND date BETWEEN %s AND %s AND adjust = 'qfq'",
                (*tickers, start, end),
            )
            return cur.fetchall()
    finally:
        conn.close()


def _parse_component(url: str, pattern: str, default: str) -> str:
    import re

    m = re.search(pattern, url)
    return m.group(1) if m else default


def _parse_host(url: str) -> str:
    return _parse_component(url, r"@([^:/?]+)", "127.0.0.1")


def _parse_user(url: str) -> str:
    return _parse_component(url, r"//([^:]+)", "root")


def _parse_password(url: str) -> str:
    return _parse_component(url, r":([^:@]+)@", "")


def _parse_db(url: str) -> str:
    return _parse_component(url, r"/(\w+)(\?|$)", "akshare")


def _parse_port(url: str) -> int:
    return int(_parse_component(url, r":(\d+)/", "3306"))


async def fetch_daily_from_mysql(
    db: AsyncSession, tickers: list[str], start: dt.date, end: dt.date
) -> int:
    """外部 MySQL 前复权日线 → 逐只拉取并立即落库（拉一只灌一只）。

    内存占用恒定（单票 ~1200 行）；本地表行数即真实进度，中断可续
    （已落库的票跳过）。同票同日重复行去重；date 升序。
    返回本次新落库的票数。BACKTEST_MYSQL_URL 为空 → raise RuntimeError。
    """
    from core.config import settings

    if not settings.BACKTEST_MYSQL_URL:
        raise RuntimeError("BACKTEST_MYSQL_URL 未配置，无法拉取历史日线")

    # 断点续传：本地已有 5 年数据的票跳过
    from market.models import StockPrice
    from sqlalchemy import func, select

    done = set(
        (
            await db.execute(
                select(StockPrice.ticker)
                .where(StockPrice.date >= start, StockPrice.date <= end)
                .group_by(StockPrice.ticker)
                .having(func.count() >= 200)  # 5 年 ~1200 交易日；<200 视为不完整重拉
            )
        ).scalars().all()
    )
    pending = [t for t in tickers if t not in done]
    logger.info("回测日线：共 %d 只，本地已有 %d 只，待拉取 %d 只", len(tickers), len(done), len(pending))

    synced = 0
    for idx, ticker in enumerate(pending, 1):
        rows: list[tuple] = []
        for attempt in range(3):
            try:
                rows = await asyncio.to_thread(
                    _fetch_daily_sync, settings.BACKTEST_MYSQL_URL, [ticker], start, end
                )
                break
            except Exception as e:  # noqa: BLE001 — 网络抖动重试（逐只拉取下单次失败不应毁掉整个 run）
                if attempt == 2:
                    raise
                logger.warning(
                    "回测日线拉取重试 %d/3 %s: %s", attempt + 1, ticker, str(e)[:120]
                )
                await asyncio.sleep(2 * (attempt + 1))
        if rows:
            bars: dict[dt.date, dict] = {}
            for symbol, date, open_, close, high, low, volume in rows:
                bars[date] = {
                    "date": date, "open": open_, "close": close,
                    "high": high, "low": low, "volume": volume,
                }
            await sync_daily_to_pg(db, {ticker: [bars[d] for d in sorted(bars)]})
            synced += 1
            await db.commit()  # 每只票立即提交：本地库即进度，崩溃不丢已完成部分
        if idx % 50 == 0 or idx == len(pending):
            logger.info("回测日线逐只拉取 %d/%d（累计落库 %d 只）", idx, len(pending), synced)
    return synced


async def fetch_all_tickers(start: dt.date, end: dt.date) -> list[str]:
    """外部库区间内 distinct symbol（不依赖本地 Company 表，含已退市票）。"""
    from core.config import settings

    if not settings.BACKTEST_MYSQL_URL:
        raise RuntimeError("BACKTEST_MYSQL_URL 未配置，无法拉取历史日线")

    def _query(url: str) -> list[str]:
        import pymysql

        conn = pymysql.connect(
            host=_parse_host(url), user=_parse_user(url), password=_parse_password(url),
            database=_parse_db(url), port=_parse_port(url), connect_timeout=10,
        )
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT symbol FROM akshare.stock_history_daily_info_entity "
                    "WHERE date BETWEEN %s AND %s AND adjust = 'qfq'",
                    (start, end),
                )
                return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    return await asyncio.to_thread(_query, settings.BACKTEST_MYSQL_URL)


async def sync_daily_to_pg(db: AsyncSession, daily: dict[str, list[dict]]) -> int:
    """灌 market.stock_prices（幂等：同 ticker 先删再插）。返回写入行数。"""
    from market.models import StockPrice

    total = 0
    for ticker, bars in daily.items():
        if not bars:
            continue
        dates = [b["date"] for b in bars]
        await db.execute(
            delete(StockPrice).where(
                StockPrice.ticker == ticker,
                StockPrice.date >= min(dates),
                StockPrice.date <= max(dates),
            )
        )
        db.add_all(
            StockPrice(
                ticker=ticker, date=b["date"], open=b["open"], close=b["close"],
                high=b["high"], low=b["low"], volume=b["volume"],
            )
            for b in bars
        )
        total += len(bars)
    return total


# ── 历史财务按期补拉 ─────────────────────────────────────────────


async def _missing_periods(db: AsyncSession, periods: list[tuple[int, str]]) -> set[tuple[int, str]]:
    """periods 中在 financial_metrics 尚无任何数据的报告期。"""
    from market.models import FinancialMetric

    if not periods:
        return set()
    present: set[tuple[int, str]] = set()
    for year, period in periods:
        row = (
            await db.execute(
                select(FinancialMetric.id).where(
                    FinancialMetric.fiscal_year == year,
                    FinancialMetric.fiscal_period == period,
                ).limit(1)
            )
        ).first()
        if row:
            present.add((year, period))
    return set(periods) - present


async def _ingest_yjbb_for_period(db: AsyncSession, date_str: str) -> int:
    """单报告期业绩报表市场级拉取入库（复用 ingest 管线）。"""
    from screener.ingest import ingest_marketwide_yjbb

    return await ingest_marketwide_yjbb(db, date_str)


async def _ingest_main_finance_for_period(db: AsyncSession, date_str: str) -> int:
    """单报告期 F10 主要指标入库（ROIC/FCFF/利息保障等因子）。"""
    from screener.ingest import ingest_marketwide_main_finance

    return await ingest_marketwide_main_finance(db, date_str)


async def ensure_financial_periods(db: AsyncSession, periods: list[tuple[int, str]]) -> int:
    """对缺失的报告期补拉财务数据；单期失败 SAVEPOINT 隔离不阻塞其他期。

    返回成功补拉的期数。
    """
    missing = await _missing_periods(db, periods)
    if not missing:
        return 0
    ok = 0
    for year, period in sorted(missing):
        date_str = _period_date_str(year, period)
        ingested = False
        for label, loader in (
            ("yjbb", _ingest_yjbb_for_period),
            ("F10 主要指标", _ingest_main_finance_for_period),
        ):
            try:
                await db.flush()
                async with db.begin_nested():
                    await loader(db, date_str)
                ingested = True
                logger.info("回测历史财务补拉完成 %s（%s）", date_str, label)
            except Exception as e:  # noqa: BLE001 — 单类失败降级
                logger.warning("回测历史财务补拉失败 %s（%s）: %s", date_str, label, e)
        if ingested:
            ok += 1
    return ok


# ── 基准指数 ─────────────────────────────────────────────────────


async def fetch_index_daily(start: dt.date, end: dt.date) -> list[dict]:
    """沪深300 指数日线（akshare stock_zh_index_daily）→ [{date, close}] 升序。"""
    import asyncio
    import json

    from market.akshare_executor import _AKSHARE_PROLOGUE, _run_child

    code = (
        _AKSHARE_PROLOGUE
        + "import akshare as ak, json\n"
        + "df = ak.stock_zh_index_daily(symbol='sh000300')\n"
        + 'print("__R__:" + json.dumps(df.to_dict(orient="records"), ensure_ascii=False, default=str))\n'
    )
    raw = await asyncio.to_thread(_run_child, code, 300)
    if not raw or raw.startswith("E:"):
        raise RuntimeError(f"指数日线拉取失败: {raw!r}")
    payload = raw.removeprefix("__R__:").strip()
    import json as _json

    rows = _json.loads(payload)
    out = []
    for r in rows:
        d = r.get("date")
        d = dt.date.fromisoformat(str(d)[:10])
        if start <= d <= end and r.get("close") is not None:
            out.append({"date": d, "close": float(r["close"])})
    out.sort(key=lambda x: x["date"])
    return out
