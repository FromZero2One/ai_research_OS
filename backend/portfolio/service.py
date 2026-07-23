"""Portfolio Center service — watchlists, holdings, and journal."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.event_service import EventLogger
from core.exceptions import DuplicateError, NotFoundError
from portfolio.models import Holding, InvestmentJournal, Watchlist, WatchlistItem


class PortfolioService:
    """Portfolio management — watchlists, holdings, journal."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.events = EventLogger(session)

    # ── Watchlists ────────────────────────────────────────────────

    async def create_watchlist(self, name: str, description: str | None = None) -> Watchlist:
        wl = Watchlist(name=name, description=description)
        self.session.add(wl)
        await self.session.flush()
        await self.session.refresh(wl, attribute_names=["items"])
        return wl

    async def get_watchlist(self, watchlist_id: uuid.UUID) -> Watchlist:
        result = await self.session.execute(
            select(Watchlist)
            .where(Watchlist.id == watchlist_id)
            .options(selectinload(Watchlist.items))
        )
        wl = result.scalar_one_or_none()
        if not wl:
            raise NotFoundError("Watchlist", str(watchlist_id))
        return wl

    async def list_watchlists(self) -> list[Watchlist]:
        result = await self.session.execute(
            select(Watchlist).options(selectinload(Watchlist.items))
        )
        return list(result.scalars().all())

    async def delete_watchlist(self, watchlist_id: uuid.UUID) -> None:
        wl = await self.get_watchlist(watchlist_id)
        await self.session.delete(wl)

    async def update_watchlist(self, watchlist_id: uuid.UUID, **kwargs) -> Watchlist:
        wl = await self.get_watchlist(watchlist_id)
        for key, val in kwargs.items():
            if val is not None:
                setattr(wl, key, val)
        await self.session.flush()
        await self.session.refresh(wl)
        return wl

    async def add_to_watchlist(
        self, watchlist_id: uuid.UUID, ticker: str, **kwargs
    ) -> WatchlistItem:
        item = WatchlistItem(watchlist_id=watchlist_id, ticker=ticker.upper(), **kwargs)
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def remove_from_watchlist(self, item_id: uuid.UUID) -> None:
        result = await self.session.execute(
            select(WatchlistItem).where(WatchlistItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            raise NotFoundError("WatchlistItem", str(item_id))
        await self.session.delete(item)

    # ── Holdings ──────────────────────────────────────────────────

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
            stmt = stmt.where(Holding.is_active == True)
        stmt = stmt.order_by(Holding.ticker)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_holding(
        self, holding_id: uuid.UUID, **kwargs
    ) -> Holding:
        result = await self.session.execute(
            select(Holding).where(Holding.id == holding_id)
        )
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

    # ── Journal ───────────────────────────────────────────────────

    async def create_journal_entry(self, **kwargs) -> InvestmentJournal:
        entry = InvestmentJournal(**kwargs)
        self.session.add(entry)
        await self.session.flush()
        await self.session.refresh(entry)
        return entry

    async def list_journal(
        self,
        entry_type: str | None = None,
        ticker: str | None = None,
        limit: int = 50,
    ) -> list[InvestmentJournal]:
        stmt = select(InvestmentJournal)
        if entry_type:
            stmt = stmt.where(InvestmentJournal.entry_type == entry_type)
        if ticker:
            stmt = stmt.where(InvestmentJournal.ticker == ticker.upper())
        stmt = stmt.order_by(desc(InvestmentJournal.created_at)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_journal_entry(self, entry_id: uuid.UUID) -> InvestmentJournal:
        result = await self.session.execute(
            select(InvestmentJournal).where(InvestmentJournal.id == entry_id)
        )
        entry = result.scalar_one_or_none()
        if not entry:
            raise NotFoundError("JournalEntry", str(entry_id))
        return entry
