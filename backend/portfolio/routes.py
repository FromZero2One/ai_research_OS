"""Portfolio Center API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from portfolio.schemas import (
    HoldingCreate,
    HoldingResponse,
    HoldingUpdate,
    JournalEntryCreate,
    JournalEntryResponse,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistResponse,
)
from portfolio.service import PortfolioService

router = APIRouter(prefix="/portfolio", tags=["Portfolio Center"])


# ── Watchlists ──────────────────────────────────────────────────────

@router.post("/watchlists", response_model=WatchlistResponse, status_code=201)
async def create_watchlist(data: WatchlistCreate, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    wl = await svc.create_watchlist(**data.model_dump())
    return WatchlistResponse.model_validate(wl)


@router.get("/watchlists", response_model=list[WatchlistResponse])
async def list_watchlists(db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    watchlists = await svc.list_watchlists()
    return [WatchlistResponse.model_validate(wl) for wl in watchlists]


@router.get("/watchlists/{watchlist_id}", response_model=WatchlistResponse)
async def get_watchlist(watchlist_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    wl = await svc.get_watchlist(watchlist_id)
    return WatchlistResponse.model_validate(wl)


@router.delete("/watchlists/{watchlist_id}", status_code=204)
async def delete_watchlist(watchlist_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    await svc.delete_watchlist(watchlist_id)


@router.post("/watchlists/{watchlist_id}/items", response_model=WatchlistItemResponse, status_code=201)
async def add_to_watchlist(
    watchlist_id: uuid.UUID, data: WatchlistItemCreate, db: AsyncSession = Depends(get_db)
):
    svc = PortfolioService(db)
    return await svc.add_to_watchlist(watchlist_id, **data.model_dump())


@router.delete("/watchlists/items/{item_id}", status_code=204)
async def remove_from_watchlist(item_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    await svc.remove_from_watchlist(item_id)


# ── Holdings ────────────────────────────────────────────────────────

@router.post("/holdings", response_model=HoldingResponse, status_code=201)
async def add_holding(data: HoldingCreate, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    return await svc.add_holding(**data.model_dump())


@router.get("/holdings", response_model=list[HoldingResponse])
async def list_holdings(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
):
    svc = PortfolioService(db)
    return await svc.get_holdings(active_only=active_only)


@router.patch("/holdings/{holding_id}", response_model=HoldingResponse)
async def update_holding(
    holding_id: uuid.UUID,
    data: HoldingUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = PortfolioService(db)
    return await svc.update_holding(holding_id, **data.model_dump(exclude_unset=True))


@router.post("/holdings/{holding_id}/close", response_model=HoldingResponse)
async def close_holding(holding_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    return await svc.close_holding(holding_id)


# ── Journal ─────────────────────────────────────────────────────────

@router.post("/journal", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(data: JournalEntryCreate, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    return await svc.create_journal_entry(**data.model_dump())


@router.get("/journal", response_model=list[JournalEntryResponse])
async def list_journal(
    entry_type: str | None = Query(None, pattern="^(idea|analysis|reflection|lesson)$"),
    ticker: str | None = None,
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    svc = PortfolioService(db)
    return await svc.list_journal(entry_type=entry_type, ticker=ticker, limit=limit)


@router.get("/journal/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = PortfolioService(db)
    return await svc.get_journal_entry(entry_id)
