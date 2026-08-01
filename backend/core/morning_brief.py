"""Morning Brief model — replaces EventLog-as-DB for brief storage."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, UUIDMixin


class MorningBrief(Base, UUIDMixin):
    """AI-generated morning brief — one per weekday."""

    __tablename__ = "morning_briefs"
    __table_args__ = {"schema": "core"}

    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    stocks_covered: Mapped[int] = mapped_column(Integer, default=0)
    focus_stocks: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
