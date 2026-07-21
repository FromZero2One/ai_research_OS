"""Portfolio Center ORM models — watchlists, holdings, investment journal."""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.base import Base, TimestampMixin, UUIDMixin


class Watchlist(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "watchlists"
    __table_args__ = {"schema": "portfolio"}

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist", cascade="all, delete-orphan"
    )


class WatchlistItem(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "watchlist_items"
    __table_args__ = {"schema": "portfolio"}

    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("portfolio.watchlists.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[int] = mapped_column(default=3, nullable=False)

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


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

    entry_type: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
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
