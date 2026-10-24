"""组合方案持久化 — 保存构建参数与结果，供历史查看/再平衡对照。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import ScreenerPortfolio


def portfolio_json(p: ScreenerPortfolio) -> dict:
    return {
        "id": str(p.id),
        "run_id": str(p.run_id),
        "name": p.name,
        "params": p.params,
        "result": p.result,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


async def save_portfolio(
    db: AsyncSession,
    run_id: uuid.UUID,
    params: dict,
    result: dict,
    name: str | None = None,
) -> ScreenerPortfolio:
    row = ScreenerPortfolio(
        run_id=run_id,
        name=(name or "").strip()[:128] or None,
        params=params,
        result=result,
    )
    db.add(row)
    await db.flush()
    return row


async def list_portfolios(
    db: AsyncSession, run_id: uuid.UUID | None = None
) -> list[ScreenerPortfolio]:
    stmt = select(ScreenerPortfolio).order_by(ScreenerPortfolio.created_at.desc())
    if run_id is not None:
        stmt = stmt.where(ScreenerPortfolio.run_id == run_id)
    return list((await db.execute(stmt)).scalars().all())


async def get_portfolio(
    db: AsyncSession, portfolio_id: uuid.UUID
) -> ScreenerPortfolio | None:
    return (
        await db.execute(
            select(ScreenerPortfolio).where(ScreenerPortfolio.id == portfolio_id)
        )
    ).scalar_one_or_none()


async def delete_portfolio(db: AsyncSession, portfolio_id: uuid.UUID) -> bool:
    row = await get_portfolio(db, portfolio_id)
    if row is None:
        return False
    await db.delete(row)
    return True
