"""Portfolio Center API routes — holdings and investment journal."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query

from core.container import Container
from core.database import get_container
from portfolio.schemas import (
    HoldingCreate,
    HoldingResponse,
    HoldingUpdate,
    JournalEntryCreate,
    JournalEntryResponse,
)

router = APIRouter(prefix="/portfolio", tags=["Portfolio Center"])


# ── Holdings ────────────────────────────────────────────────────────


@router.post("/holdings", response_model=HoldingResponse, status_code=201)
async def add_holding(
    data: HoldingCreate,
    container: Container = Depends(get_container),
):
    svc = container.holding_service
    return await svc.add_holding(**data.model_dump())


@router.get("/holdings", response_model=list[HoldingResponse])
async def list_holdings(
    active_only: bool = True,
    container: Container = Depends(get_container),
):
    svc = container.holding_service
    return await svc.get_holdings(active_only=active_only)


@router.patch("/holdings/{holding_id}", response_model=HoldingResponse)
async def update_holding(
    holding_id: uuid.UUID,
    data: HoldingUpdate,
    container: Container = Depends(get_container),
):
    svc = container.holding_service
    return await svc.update_holding(holding_id, **data.model_dump(exclude_unset=True))


@router.post("/holdings/{holding_id}/close", response_model=HoldingResponse)
async def close_holding(
    holding_id: uuid.UUID,
    container: Container = Depends(get_container),
):
    svc = container.holding_service
    return await svc.close_holding(holding_id)


# ── Journal ─────────────────────────────────────────────────────────


@router.post("/journal", response_model=JournalEntryResponse, status_code=201)
async def create_journal_entry(
    data: JournalEntryCreate,
    container: Container = Depends(get_container),
):
    svc = container.journal_service
    return await svc.create_journal_entry(**data.model_dump())


@router.get("/journal", response_model=list[JournalEntryResponse])
async def list_journal(
    entry_type: str | None = Query(None, pattern="^(idea|analysis|reflection|lesson)$"),
    ticker: str | None = None,
    limit: int = Query(50, le=200),
    container: Container = Depends(get_container),
):
    svc = container.journal_service
    return await svc.list_journal(entry_type=entry_type, ticker=ticker, limit=limit)


@router.get("/journal/{entry_id}", response_model=JournalEntryResponse)
async def get_journal_entry(
    entry_id: uuid.UUID,
    container: Container = Depends(get_container),
):
    svc = container.journal_service
    return await svc.get_journal_entry(entry_id)
