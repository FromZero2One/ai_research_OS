"""Market Center domain models — pure business DTOs.

These are ORM-free value objects used by services and routes. They give
callers a stable, typed contract regardless of the underlying data source
(PostgreSQL, MySQL, akshare, yfinance). Mappers to/from ORM models live on
the classes as ``from_model`` / ``to_model``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


@dataclass(slots=True)
class PriceEntry:
    """One day of price data for a ticker."""

    date: date
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    adjusted_close: float | None = None

    @classmethod
    def from_model(cls, model: Any) -> PriceEntry:
        return cls(
            date=model.date,
            open=model.open,
            high=model.high,
            low=model.low,
            close=model.close,
            volume=model.volume,
            adjusted_close=model.adjusted_close,
        )

    @classmethod
    def from_row(cls, row: dict) -> PriceEntry:
        """Build from a raw dict (akshare/yfinance row)."""
        date_val = row.get("date")
        if isinstance(date_val, datetime):
            date_val = date_val.date()
        elif isinstance(date_val, str):
            date_val = date.fromisoformat(date_val[:10])
        if not isinstance(date_val, date):
            raise ValueError(f"Invalid date in price row: {date_val!r}")
        return cls(
            date=date_val,
            open=row.get("open"),
            high=row.get("high"),
            low=row.get("low"),
            close=row.get("close"),
            volume=row.get("volume"),
            adjusted_close=row.get("adjusted_close"),
        )

    def to_model(self, model_cls: Any, ticker: str) -> Any:
        return model_cls(
            ticker=ticker.upper(),
            date=self.date,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            adjusted_close=self.adjusted_close,
        )

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "adjusted_close": self.adjusted_close,
        }


@dataclass(slots=True)
class FinancialMetricEntry:
    """One financial metric value for a ticker."""

    fiscal_year: int
    fiscal_period: str
    metric_name: str
    metric_value: float | None = None
    reported_at: datetime | None = None

    @classmethod
    def from_model(cls, model: Any) -> FinancialMetricEntry:
        return cls(
            fiscal_year=model.fiscal_year,
            fiscal_period=model.fiscal_period,
            metric_name=model.metric_name,
            metric_value=model.metric_value,
            reported_at=model.reported_at,
        )

    @classmethod
    def from_row(cls, row: dict) -> FinancialMetricEntry:
        fiscal_year = row.get("fiscal_year")
        metric_name = row.get("metric_name")
        if fiscal_year is None or metric_name is None:
            raise ValueError("Missing fiscal_year/metric_name in financial row")
        return cls(
            fiscal_year=int(fiscal_year),
            fiscal_period=row.get("fiscal_period", "Annual"),
            metric_name=str(metric_name),
            metric_value=row.get("metric_value"),
            reported_at=row.get("reported_at"),
        )

    def to_model(self, model_cls: Any, ticker: str) -> Any:
        return model_cls(
            ticker=ticker.upper(),
            fiscal_year=self.fiscal_year,
            fiscal_period=self.fiscal_period,
            metric_name=self.metric_name,
            metric_value=self.metric_value,
            reported_at=self.reported_at,
        )

    def as_dict(self) -> dict:
        return {
            "fiscal_year": self.fiscal_year,
            "fiscal_period": self.fiscal_period,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "reported_at": self.reported_at.isoformat() if self.reported_at else None,
        }


@dataclass(slots=True)
class FreshnessEntry:
    """Freshness record for one (ticker, data_type) pair."""

    ticker: str
    data_type: str
    last_fetched_at: datetime | None = None
    record_count: int = 0
    status: str = "ok"
    error_message: str | None = None

    @classmethod
    def from_model(cls, model: Any) -> FreshnessEntry:
        return cls(
            ticker=model.ticker,
            data_type=model.data_type,
            last_fetched_at=model.last_fetched_at,
            record_count=model.record_count,
            status=model.status,
            error_message=model.error_message,
        )

    def as_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "data_type": self.data_type,
            "last_fetched_at": self.last_fetched_at.isoformat() if self.last_fetched_at else None,
            "record_count": self.record_count,
            "status": self.status,
            "error_message": self.error_message,
        }
