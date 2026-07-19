"""Market Center ORM models — prices, financials, macros."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, TimestampMixin, UUIDMixin


class StockPrice(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stock_prices"
    __table_args__ = {"schema": "market"}

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjusted_close: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Composite unique: one row per ticker per date
    __table_args__ = (
        {"schema": "market"},
    )


class FinancialMetric(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "financial_metrics"
    __table_args__ = {"schema": "market"}

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(16), nullable=False)  # Q1/Q2/Q3/Q4/Annual
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(nullable=True)


class MacroIndicator(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "macro_indicators"
    __table_args__ = {"schema": "market"}

    indicator: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)
