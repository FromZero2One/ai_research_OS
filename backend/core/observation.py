"""Observation model — replaces EventLog-as-DB for watchlist observations."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, UUIDMixin


class Observation(Base, UUIDMixin):
    """Watchlist observation — generated daily by the observation engine."""

    __tablename__ = "observations"
    __table_args__ = {"schema": "core"}

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(256), nullable=False)
    reasons: Mapped[str] = mapped_column(Text, nullable=False)  # newline-separated
    status: Mapped[str] = mapped_column(String(32), default="attention")  # attention | need_research
    days_since_research: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
