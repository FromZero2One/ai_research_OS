"""Holding service — position tracking and updates."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.event_service import EventLogger
from core.exceptions import NotFoundError
from portfolio.models import Holding


class HoldingService:
    """Holding (position) management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    async def add_holding(self, ticker: str, shares: float, **kwargs) -> Holding:
        holding = Holding(ticker=ticker.upper(), shares=shares, **kwargs)
        self.session.add(holding)
        await self.session.flush()
        await self.session.refresh(holding)
        await self.events.record(
            source="portfolio",
            event_type="holding.added",
            entity_type="holding",
            entity_id=str(holding.id),
            payload={"ticker": ticker, "shares": shares},
        )
        return holding

    async def get_holdings(self, active_only: bool = True) -> list[Holding]:
        stmt = select(Holding)
        if active_only:
            stmt = stmt.where(Holding.is_active.is_(True))
        stmt = stmt.order_by(Holding.ticker)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_holding(self, holding_id: uuid.UUID, **kwargs) -> Holding:
        result = await self.session.execute(select(Holding).where(Holding.id == holding_id))
        holding = result.scalar_one_or_none()
        if not holding:
            raise NotFoundError("Holding", str(holding_id))

        for key, val in kwargs.items():
            if val is not None:
                setattr(holding, key, val)
        await self.session.flush()
        await self.session.refresh(holding)
        return holding

    async def close_holding(self, holding_id: uuid.UUID) -> Holding:
        return await self.update_holding(holding_id, is_active=False)
