"""跨模块共享的批量查询。

- 自选公司加载（is_active，watchlist 语义已合并进 Company）
- 每 ticker 最新价格
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company
from market.models import StockPrice


async def load_watched_companies(session: AsyncSession) -> list[Company]:
    """加载自选公司（watched == is_active）。"""
    result = await session.execute(select(Company).where(Company.is_active.is_(True)))
    return list(result.scalars().all())


async def latest_price_by_ticker(
    session: AsyncSession,
    tickers: list[str],
) -> dict[str, StockPrice]:
    """批量取每 ticker 最新一条价格（GROUP BY → max date 子查询）。"""
    if not tickers:
        return {}
    subq = (
        select(StockPrice.ticker, func.max(StockPrice.date).label("max_date"))
        .where(StockPrice.ticker.in_(tickers))
        .group_by(StockPrice.ticker)
        .subquery()
    )
    latest_px = await session.execute(
        select(StockPrice).join(
            subq,
            (StockPrice.ticker == subq.c.ticker) & (StockPrice.date == subq.c.max_date),
        )
    )
    return {p.ticker: p for p in latest_px.scalars().all()}
