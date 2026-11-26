"""Company Center ORM models."""

from __future__ import annotations

from sqlalchemy import Boolean, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, TimestampMixin, UUIDMixin


class Company(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = {"schema": "company"}

    ticker: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    headquarters: Mapped[str | None] = mapped_column(String(256), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(nullable=True)
    employees: Mapped[int | None] = mapped_column(nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Watchlist semantics merged into the company row: watched == is_active.
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    target_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
