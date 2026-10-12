"""Market Center ORM models — prices, financials, macros."""

from __future__ import annotations

from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, TimestampMixin, UUIDMixin


class StockPrice(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "stock_prices"

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[float | None] = mapped_column(Float, nullable=True)
    high: Mapped[float | None] = mapped_column(Float, nullable=True)
    low: Mapped[float | None] = mapped_column(Float, nullable=True)
    close: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume: Mapped[float | None] = mapped_column(Float, nullable=True)
    adjusted_close: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Composite unique: one row per ticker per date
    __table_args__: tuple[dict[str, str], ...] = ({"schema": "market"},)


class FinancialMetricName(StrEnum):
    """标准化财务指标名称（值即数据库中存储的字符串，兼容历史数据）。"""

    REVENUE = "revenue"
    NET_INCOME = "net_income"
    GROSS_PROFIT = "gross_profit"
    OPERATING_INCOME = "operating_income"
    EBITDA = "ebitda"
    ROE = "roe"
    ROA = "roa"
    EPS = "eps"
    DIVIDEND_PER_SHARE = "dividend_per_share"
    DIVIDEND_YIELD = "dividend_yield"
    MARKET_CAP = "market_cap"
    BOOK_VALUE = "book_value"
    CURRENT_RATIO = "current_ratio"
    QUICK_RATIO = "quick_ratio"
    DEBT_TO_EQUITY = "debt_to_equity"
    ASSET_TURNOVER = "asset_turnover"
    INVENTORY_TURNOVER = "inventory_turnover"
    RECEIVABLES_TURNOVER = "receivables_turnover"
    FREE_CASH_FLOW = "free_cash_flow"
    CAPEX = "capex"
    TAX_RATE = "tax_rate"


class FinancialMetricUnit(StrEnum):
    """标准化财务指标单位（值即存储字符串）。"""

    YUAN = "元"
    YUAN_10K = "万元"
    YUAN_100M = "亿元"
    PERCENT = "%"
    RATIO = "倍"
    SHARES = "股"


# 中文指标名 → 标准枚举值（用于入库前归一化）
_METRIC_NAME_CN_MAP: dict[str, str] = {
    "营业收入": "revenue",
    "营收": "revenue",
    "净利润": "net_income",
    "毛利润": "gross_profit",
    "营业利润": "operating_income",
    "净资产收益率": "roe",
    "总资产收益率": "roa",
    "每股收益": "eps",
    "每股分红": "dividend_per_share",
    "股息率": "dividend_yield",
    "总市值": "market_cap",
    "账面价值": "book_value",
    "流动比率": "current_ratio",
    "速动比率": "quick_ratio",
    "资产负债率": "debt_to_equity",
    "总资产周转率": "asset_turnover",
    "存货周转率": "inventory_turnover",
    "应收账款周转率": "receivables_turnover",
    "自由现金流": "free_cash_flow",
    "资本支出": "capex",
    "实际税率": "tax_rate",
}


def normalize_metric_name(name: str) -> str:
    """把中文/别名指标名归一化为标准枚举值；未知名称原样返回（小写化）。"""
    return _METRIC_NAME_CN_MAP.get(name, name.strip().lower())


class FinancialMetric(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "financial_metrics"
    __table_args__ = {"schema": "market"}

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    fiscal_year: Mapped[int] = mapped_column(nullable=False)
    fiscal_period: Mapped[str] = mapped_column(String(16), nullable=False)  # Q1/Q2/Q3/Q4/Annual
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    """存储归一化后的标准名（FinancialMetricName 值），历史数据保持原值兼容读取"""

    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    metric_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """标准单位（FinancialMetricUnit 值），历史数据为 NULL"""

    reported_at: Mapped[datetime | None] = mapped_column(nullable=True)


class MacroIndicator(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "macro_indicators"
    __table_args__ = {"schema": "market"}

    indicator: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DataFreshness(Base, UUIDMixin, TimestampMixin):
    """Per-ticker data freshness tracking — when was each data type last fetched.

    One row per (ticker, data_type) combination, upserted on each successful fetch.
    """

    __tablename__ = "data_freshness"
    __table_args__ = ({"schema": "market"},)

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    """prices | financials | profile | news"""

    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    """When the data was last successfully fetched."""

    record_count: Mapped[int | None] = mapped_column(nullable=True)
    """How many records were fetched (e.g. number of price rows)."""

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    """ok | stale | error | never_fetched"""

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
