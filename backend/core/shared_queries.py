"""跨模块共享的批量查询 — dashboard 使用的取数管道（原三份重复实现抽取）。

从 dashboard/service.py 与（已移除的）core/brief_generator.py 的三份重复实现中抽取：
- 自选公司加载（is_active，watchlist 语义已合并进 Company）
- 每公司最新研究会话（原 dashboard 内部两份 + brief 一份，共三写）
- 每 ticker 最新价格（原 dashboard 与 brief 各一份，实现各异）
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company
from market.models import StockPrice
from research.models import ResearchSession


async def load_watched_companies(session: AsyncSession) -> list[Company]:
    """加载自选公司（watched == is_active）。"""
    result = await session.execute(select(Company).where(Company.is_active.is_(True)))
    return list(result.scalars().all())


async def latest_research_by_company(
    session: AsyncSession,
    company_ids: list[uuid.UUID],
) -> dict[uuid.UUID, ResearchSession]:
    """批量取每公司最新一次研究会话（GROUP BY → max created_at 子查询）。"""
    if not company_ids:
        return {}
    subq = (
        select(
            ResearchSession.company_id,
            func.max(ResearchSession.created_at).label("max_created"),
        )
        .where(ResearchSession.company_id.in_(company_ids))
        .group_by(ResearchSession.company_id)
        .subquery()
    )
    rs_result = await session.execute(
        select(ResearchSession).join(
            subq,
            (ResearchSession.company_id == subq.c.company_id)
            & (ResearchSession.created_at == subq.c.max_created),
        )
    )
    return {rs.company_id: rs for rs in rs_result.scalars().all() if rs.company_id is not None}


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
