"""Journal service — investment journal entries."""

from __future__ import annotations

import uuid

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import NotFoundError
from portfolio.models import InvestmentJournal


class JournalService:
    """Investment journal management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

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
