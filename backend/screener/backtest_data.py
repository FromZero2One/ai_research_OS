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
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger
from screener import backtest

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
        host=_parse_host(url),
        user=_parse_user(url),
        password=_parse_password(url),
        database=_parse_db(url),
        port=_parse_port(url),
        connect_timeout=10,
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
    from sqlalchemy import func, select

    from market.models import StockPrice

    done = set(
        (
            await db.execute(
                select(StockPrice.ticker)
                .where(StockPrice.date >= start, StockPrice.date <= end)
                .group_by(StockPrice.ticker)
                .having(func.count() >= 200)  # 5 年 ~1200 交易日；<200 视为不完整重拉
            )
        )
        .scalars()
        .all()
    )
    pending = [t for t in tickers if t not in done]
    logger.info(
        "回测日线：共 %d 只，本地已有 %d 只，待拉取 %d 只", len(tickers), len(done), len(pending)
    )

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
                logger.warning("回测日线拉取重试 %d/3 %s: %s", attempt + 1, ticker, str(e)[:120])
                await asyncio.sleep(2 * (attempt + 1))
        if rows:
            bars: dict[dt.date, dict] = {}
            for symbol, date, open_, close, high, low, volume in rows:
                bars[date] = {
                    "date": date,
                    "open": open_,
                    "close": close,
                    "high": high,
                    "low": low,
                    "volume": volume,
                }
            await sync_daily_to_pg(db, {ticker: [bars[d] for d in sorted(bars)]})
            synced += 1
            await db.commit()  # 每只票立即提交：本地库即进度，崩溃不丢已完成部分
        if idx % 50 == 0 or idx == len(pending):
            logger.info("回测日线逐只拉取 %d/%d（累计落库 %d 只）", idx, len(pending), synced)
    return synced


_all_tickers_cache: list[str] | None = None


async def fetch_all_tickers(start: dt.date, end: dt.date) -> list[str]:
    """全市场票池：优先轻量表 stock_name_entity（毫秒级），空则回退区间 DISTINCT 大表。

    大表（1600 万行）上做 DISTINCT 无索引、公共库上可能耗时数分钟，仅作兜底；
    结果进程内缓存，避免每次回测重复查询。
    """
    from core.config import settings

    if not settings.BACKTEST_MYSQL_URL:
        raise RuntimeError("BACKTEST_MYSQL_URL 未配置，无法拉取历史日线")

    global _all_tickers_cache
    if _all_tickers_cache:
        return _all_tickers_cache

    def _query(url: str) -> list[str]:
        import pymysql

        conn = pymysql.connect(
            host=_parse_host(url),
            user=_parse_user(url),
            password=_parse_password(url),
            database=_parse_db(url),
            port=_parse_port(url),
            connect_timeout=10,
            read_timeout=120,
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT symbol FROM akshare.stock_name_entity")
                rows = [r[0] for r in cur.fetchall()]
                if rows:
                    return rows
                cur.execute(
                    "SELECT DISTINCT symbol FROM akshare.stock_history_daily_info_entity "
                    "WHERE date BETWEEN %s AND %s AND adjust = 'qfq'",
                    (start, end),
                )
                return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    _all_tickers_cache = await asyncio.to_thread(_query, settings.BACKTEST_MYSQL_URL)
    logger.info("全市场票池：%d 只（stock_name_entity）", len(_all_tickers_cache))
    return _all_tickers_cache


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
                ticker=ticker,
                date=b["date"],
                open=b["open"],
                close=b["close"],
                high=b["high"],
                low=b["low"],
                volume=b["volume"],
            )
            for b in bars
        )
        total += len(bars)
    return total


# ── 历史财务按期补拉 ─────────────────────────────────────────────


async def _load_financials_by_period(
    db: AsyncSession,
    periods: list[tuple[int, str]],
    asof_by_period: dict[tuple[int, str], dt.date] | None = None,
) -> dict[tuple[int, str], dict[str, list]]:
    """{(year, period): {ticker: [FinancialMetricEntry]}}（仅所需报告期）。

    Point-in-Time（截止日口径）：报告期法定披露截止日之后的调仓才可见。
    东财 yjbb 的“最新公告日期”是**滚动最新值**（历史期会被污染成后续期公告日），
    因此把公告日钳制到报告期截止日，避免历史期被整体误排除；缺失公告日同样按
    截止日处理（回测报告会声明口径）。
    """
    from market.domain import FinancialMetricEntry
    from market.models import FinancialMetric

    deadlines = backtest.build_disclosure_map()
    out: dict[tuple[int, str], dict[str, list]] = defaultdict(dict)
    for year, period in periods:
        rows = (
            (
                await db.execute(
                    select(FinancialMetric).where(
                        FinancialMetric.fiscal_year == year,
                        FinancialMetric.fiscal_period == period,
                    )
                )
            )
            .scalars()
            .all()
        )

        deadline = deadlines.get((year, period))
        # 同票同期取最晚公告日（期末报告/更正），作为该票该期的可见日
        announcements: dict[str, dt.date] = {}
        for m in rows:
            if m.announcement_date is None:
                continue
            previous = announcements.get(m.ticker)
            if previous is None or m.announcement_date > previous:
                announcements[m.ticker] = m.announcement_date

        asof = (asof_by_period or {}).get((year, period))
        by_ticker: dict[str, list] = defaultdict(list)
        for m in rows:
            announced = m.announcement_date or announcements.get(m.ticker)
            # 滚动公告日 → 钳制到本期披露截止日（截止日为空则沿用原值）
            if deadline is not None and announced is not None and announced > deadline:
                announced = deadline
            if asof is not None and announced is not None and announced > asof:
                continue
            by_ticker[m.ticker].append(
                FinancialMetricEntry(
                    fiscal_year=m.fiscal_year,
                    fiscal_period=m.fiscal_period,
                    metric_name=m.metric_name,
                    metric_value=m.metric_value,
                    announcement_date=m.announcement_date,
                )
            )
        out[(year, period)] = dict(by_ticker)
    return dict(out)


_REQUIRED_METRICS = ("eps", "total_assets", "operating_cash_flow")
# F10 主要指标族（ROIC/FCFF/流动比率等），至少出现一个才算该期已补齐
_F10_MARKERS = ("roic", "fcff", "current_ratio")


async def _missing_periods(
    db: AsyncSession, periods: list[tuple[int, str]]
) -> set[tuple[int, str]]:
    """periods 中缺少关键指标族（利润表/资产负债表/现金流）的报告期。"""
    from market.models import FinancialMetric

    if not periods:
        return set()
    present: dict[tuple[int, str], set[str]] = {}
    for year, period in periods:
        rows = (
            (
                await db.execute(
                    select(FinancialMetric.metric_name)
                    .where(
                        FinancialMetric.fiscal_year == year,
                        FinancialMetric.fiscal_period == period,
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
        present[(year, period)] = set(rows)
    return {
        (y, p)
        for (y, p) in periods
        if not all(m in present[(y, p)] for m in _REQUIRED_METRICS)
        or not any(m in present[(y, p)] for m in _F10_MARKERS)
    }


async def _ingest_yjbb_for_period(db: AsyncSession, date_str: str) -> int:
    """单报告期业绩报表市场级拉取入库（复用 ingest 管线）。"""
    from screener.ingest import ingest_marketwide_yjbb

    return await ingest_marketwide_yjbb(db, date_str)


async def _ingest_zcfz_for_period(db: AsyncSession, date_str: str) -> int:
    """单报告期资产负债表入库（total_assets / total_liabilities / debt_to_equity）。"""
    from screener.ingest import ingest_marketwide_zcfz

    return await ingest_marketwide_zcfz(db, date_str)


async def _ingest_xjll_for_period(db: AsyncSession, date_str: str) -> int:
    """单报告期现金流量表入库（operating_cash_flow）。"""
    from screener.ingest import ingest_marketwide_xjll

    return await ingest_marketwide_xjll(db, date_str)


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
            ("资产负债表", _ingest_zcfz_for_period),
            ("现金流量表", _ingest_xjll_for_period),
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

    from screener.ingest import _AKSHARE_PROLOGUE, _run_child

    code = (
        _AKSHARE_PROLOGUE
        + "import akshare as ak, json\n"
        + "df = ak.stock_zh_index_daily(symbol='sh000300')\n"
        + 'print("__R__:" + json.dumps(df.to_dict(orient="records"), '
        "ensure_ascii=False, default=str))\n"
    )
    rows = await asyncio.to_thread(_run_child, code, 300)
    if not rows:
        raise RuntimeError(f"指数日线拉取失败: {rows!r}")
    out = []
    for r in rows:
        d = r.get("date")
        d = dt.date.fromisoformat(str(d)[:10])
        if start <= d <= end and r.get("close") is not None:
            out.append({"date": d, "close": float(r["close"])})
    out.sort(key=lambda x: x["date"])
    return out


# ── 价格快照 / 总股本 / 基准收益 ────────────────────────────────


async def _price_dates_from_pg(db: AsyncSession, start: dt.date, end: dt.date) -> list[dt.date]:
    """区间内实际交易日历（从已灌入的日线推导）。"""
    from market.models import StockPrice

    rows = (
        (
            await db.execute(
                select(StockPrice.date)
                .where(StockPrice.date >= start, StockPrice.date <= end)
                .distinct()
                .order_by(StockPrice.date)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def _load_day_closes(db: AsyncSession, day: dt.date, tickers: list[str]) -> dict[str, float]:
    """某交易日各票前复权收盘价。"""
    from market.models import StockPrice

    rows = (
        await db.execute(
            select(StockPrice.ticker, StockPrice.close).where(
                StockPrice.date == day, StockPrice.ticker.in_(tickers)
            )
        )
    ).all()
    return {t: c for t, c in rows if c is not None}


async def _load_day_volumes(
    db: AsyncSession, day: dt.date, tickers: list[str]
) -> dict[str, float | None]:
    """某交易日成交量（用于停牌/不可交易判断）。"""
    from market.models import StockPrice

    rows = (
        await db.execute(
            select(StockPrice.ticker, StockPrice.volume).where(
                StockPrice.date == day, StockPrice.ticker.in_(tickers)
            )
        )
    ).all()
    return {t: v for t, v in rows}


def _fetch_shares_sync(url: str) -> dict[str, float]:
    """外部库最新交易日的总股本快照（symbol → TOTAL_SHARES）。"""
    import pymysql

    conn = pymysql.connect(
        host=_parse_host(url),
        user=_parse_user(url),
        password=_parse_password(url),
        database=_parse_db(url),
        port=_parse_port(url),
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT v.symbol, v.TOTAL_SHARES FROM akshare.stock_value_entity v "
                "JOIN (SELECT max(TRADE_DATE) d FROM akshare.stock_value_entity) m "
                "ON v.TRADE_DATE = m.d "
                "WHERE v.TOTAL_SHARES IS NOT NULL AND v.TOTAL_SHARES > 0"
            )
            return {str(sym).strip(): float(sh) for sym, sh in cur.fetchall()}
    finally:
        conn.close()


async def _fetch_total_shares(db: AsyncSession, tickers: list[str]) -> dict[str, float]:
    """当前总股本（近似市值用）：外部库 stock_value_entity 最新快照优先，akshare 兜底。

    返回 {ticker: 总股本}；缺失的票不在返回中（该票 market_cap=None）。
    """
    from core.config import settings

    want = set(tickers)
    if settings.BACKTEST_MYSQL_URL:
        try:
            all_shares = await asyncio.to_thread(_fetch_shares_sync, settings.BACKTEST_MYSQL_URL)
            out = {t: all_shares[t] for t in want if all_shares.get(t, 0) > 0}
            if out:
                logger.info("总股本：外部库快照命中 %d/%d 只", len(out), len(want))
                return out
            logger.warning("外部库总股本快照为空，回退 akshare")
        except Exception as e:  # noqa: BLE001 — 外部库失败回退 akshare
            logger.warning("外部库总股本拉取失败，回退 akshare: %s", str(e)[:150])

    # 兜底：akshare 东财快照（可能被风控，失败则市值规则整体缺数据）
    from screener.ingest import _AKSHARE_PROLOGUE, _run_child

    code = (
        _AKSHARE_PROLOGUE
        + "import akshare as ak, json\n"
        + "df = ak.stock_zh_a_spot_em()\n"
        + 'cols = {"代码": "ticker", "总股本": "shares"}\n'
        + "df = df[list(cols)].rename(columns=cols)\n"
        + 'print("__R__:" + json.dumps(df.to_dict(orient="records"), '
        "ensure_ascii=False, default=str))\n"
    )
    try:
        rows = await asyncio.to_thread(_run_child, code, 300)
    except Exception as e:  # noqa: BLE001 — 兜底数据源失败不应毁掉整个回测
        logger.warning("总股本兜底拉取失败，市值规则将缺数据: %s", str(e)[:150])
        return {}
    if not rows:
        logger.warning("总股本拉取失败，市值规则将全部缺数据")
        return {}
    out: dict[str, float] = {}
    for r in rows:
        t = str(r.get("ticker", "")).strip()
        if t in want and r.get("shares") not in (None, "", "-"):
            try:
                out[t] = float(r["shares"])
            except (TypeError, ValueError):
                continue
    return out


def _bench_return(bench: list[dict], buy_day: dt.date, sell_day: dt.date) -> float:
    """基准在 [buy_day, sell_day] 的收益（取区间内首末收盘）。"""
    in_window = [b["close"] for b in bench if buy_day <= b["date"] <= sell_day]
    if len(in_window) < 2 or not in_window[0]:
        return 0.0
    return in_window[-1] / in_window[0] - 1.0
