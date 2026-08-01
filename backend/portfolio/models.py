"""Portfolio Center ORM models — holdings, investment journal.

The watchlist concept merged into Company (watched == is_active).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, TimestampMixin, UUIDMixin


class Holding(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "holdings"
    __table_args__ = {"schema": "portfolio"}

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    shares: Mapped[float] = mapped_column(Float, nullable=False)
    avg_cost_basis: Mapped[float | None] = mapped_column(Float, nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)


class InvestmentJournal(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "investment_journal"
    __table_args__ = {"schema": "portfolio"}

    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    """idea, analysis, reflection, lesson"""

    ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    research_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research.research_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
