"""Scheduled job: daily market data synchronization (market-wide A-share snapshot).

每天一次全市场快照（新浪 Market_Center，~5,400 只）→ 批量 upsert 当日 OHLCV。
不再逐只拉全历史（那样 5,000 只会跑十几小时），也不依赖 Company.is_active
（之前只刷新 8 只种子美股，导致 A 股行情永不更新）。
"""

from __future__ import annotations

import asyncio
import datetime as dt
import re

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.database import managed_session
from core.logging import logger
from market.models import StockPrice

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "Chrome/120 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
}
_INDEX_URL = "https://hq.sinajs.cn/list=sh000001"
_SNAPSHOT_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData"
)


async def _latest_trading_date(client: httpx.AsyncClient) -> dt.date | None:
    """最近交易日：新浪指数行情文本内含 YYYY-MM-DD（收盘后即为当日）。"""
    resp = await client.get(_INDEX_URL)
    match = re.search(r"(\d{4}-\d{2}-\d{2})", resp.text)
    return dt.date.fromisoformat(match.group(1)) if match else None


async def _fetch_snapshot(client: httpx.AsyncClient) -> list[dict]:
    """全市场 A 股快照（分页，每页 80 只）：code/open/high/low/close/volume。"""
    rows: list[dict] = []
    page = 1
    while True:
        data = None
        for attempt in range(3):
            try:
                resp = await client.get(
                    _SNAPSHOT_URL,
                    params={
                        "page": page,
                        "num": 80,
                        "sort": "symbol",
                        "asc": 1,
                        "node": "hs_a",
                    },
                )
                data = resp.json()
                break
            except Exception:  # noqa: BLE001 — 单页失败重试
                await asyncio.sleep(2 * (attempt + 1))
        if data is None:
            raise RuntimeError(f"Sina snapshot page {page} failed after retries")
        if not data:
            break
        for item in data:
            code = str(item.get("code") or "").strip()
            close = item.get("trade")
            if len(code) != 6 or close in (None, "", 0, 0.0):
                continue
            rows.append(
                {
                    "ticker": code,
                    "open": item.get("open") or None,
                    "high": item.get("high") or None,
                    "low": item.get("low") or None,
                    "close": close,
                    "volume": item.get("volume") or None,
                }
            )
        page += 1
        await asyncio.sleep(0.3)  # 节流，避免触发新浪风控
    return rows


async def market_data_update() -> dict:
    """全市场 A 股日更：一次快照 → 批量 upsert 最近交易日的 OHLCV。

    幂等：(ticker, date) 唯一约束 + ON CONFLICT DO NOTHING。
    非交易日/数据已最新 → 直接跳过，不制造假 bar。
    """
    async with managed_session() as session:
        latest = (await session.execute(select(func.max(StockPrice.date)))).scalar()

    async with httpx.AsyncClient(headers=_HEADERS, timeout=20, trust_env=False) as client:
        target = await _latest_trading_date(client)
        if target is None:
            logger.warning("Market data update: 无法获取最近交易日，跳过")
            return {"status": "skipped", "reason": "no_trading_date"}
        if latest is not None and target <= latest:
            logger.info(
                "Market data update: 最近交易日 %s 已覆盖（本地最新 %s），跳过",
                target,
                latest,
            )
            return {"status": "up_to_date", "date": str(target), "rows": 0}
        rows = await _fetch_snapshot(client)

    if not rows:
        logger.warning("Market data update: 快照为空，跳过")
        return {"status": "skipped", "reason": "empty_snapshot", "date": str(target)}

    payload = [{**row, "date": target, "adjusted_close": None} for row in rows]
    async with managed_session() as session:
        stmt = pg_insert(StockPrice).values(payload).on_conflict_do_nothing(
            index_elements=["ticker", "date"]
        )
        await session.execute(stmt)
        await session.commit()

    logger.info("Market data update: %s 批量写入 %d 只", target, len(payload))
    return {"status": "ok", "date": str(target), "rows": len(payload)}
