"""Watchlist service — watchlist CRUD and item management."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.exceptions import NotFoundError
from portfolio.models import Watchlist, WatchlistItem


class WatchlistService:
    """Watchlist management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
