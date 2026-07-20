"""Seed market price data for development companies.

Generates synthetic but realistic daily price data and financial metrics
for the 8 seed companies in the database.
"""

from __future__ import annotations

import asyncio
import math
import random
from datetime import date, timedelta

from sqlalchemy import select

from core.database import async_session_factory
from core.logging import configure_logging, logger

# Realistic base prices and volatility for each ticker
COMPANY_PRICES = {
    "AAPL":  {"base": 220},
    "MSFT":  {"base": 430},
    "GOOGL": {"base": 175},
    "AMZN":  {"base": 195},
    "NVDA":  {"base": 115},
    "TSLA":  {"base": 250},
    "JPM":   {"base": 200},
    "BRK.B": {"base": 430},
}


async def seed_market_data() -> int:
    """Generate and insert market data for all companies."""
    from company.models import Company
    from market.models import FinancialMetric, StockPrice

    configure_logging()
    logger.info("Seeding market data...")

    async with async_session_factory() as session:
        result = await session.execute(select(Company))
        companies = list(result.scalars().all())
        logger.info("Found %d companies", len(companies))

        total_prices = 0
        total_financials = 0

        for company in companies:
            ticker = company.ticker
            info = COMPANY_PRICES.get(ticker, {"base": 100})
            base_price = info["base"]
            vol = base_price * 0.02  # 2% daily volatility

            # ── Daily prices (2 years) ──
            prices = []
            end_date = date(2026, 7, 19)
            start_date = end_date - timedelta(days=730)

            # Random walk with drift
            price = base_price * (1 + random.uniform(-0.1, 0.1))
            current = start_date
            day_count = 0

            while current <= end_date:
                if current.weekday() < 5:  # Weekdays only
                    # Add small upward drift + random noise
                    drift = base_price * 0.0002  # ~5% annual drift
                    change = random.gauss(0, 1) * vol + drift
                    price = max(price + change, base_price * 0.5)
                    price = min(price, base_price * 2.0)

                    daily_vol = price * random.uniform(0.01, 0.04)
                    high = price + abs(random.gauss(0, 1) * daily_vol)
                    low = price - abs(random.gauss(0, 1) * daily_vol)
                    open_p = random.uniform(low, high)

                    prices.append(StockPrice(
                        ticker=ticker,
                        date=current,
                        open=round(open_p, 2),
                        high=round(max(high, open_p, price), 2),
                        low=round(min(low, open_p, price), 2),
                        close=round(price, 2),
                        volume=round(random.uniform(10_000_000, 100_000_000)),
                    ))
                    day_count += 1
                current += timedelta(days=1)

            # Batch insert prices
            session.add_all(prices)
            await session.flush()
            total_prices += day_count
            logger.info("  %s: %d price rows", ticker, day_count)

            # ── Financial metrics (4 quarters × 2 years) ──
            metrics_data = []
            for year_offset in range(2):
                fiscal_year = 2025 - year_offset
                revenue_base = base_price * random.uniform(50, 200) * 1_000_000

                for q in range(1, 5):
                    quarter_revenue = revenue_base * random.uniform(0.2, 0.3)
                    quarter_profit = quarter_revenue * random.uniform(0.15, 0.35)

                    metrics_data.extend([
                        FinancialMetric(
                            ticker=ticker, fiscal_year=fiscal_year,
                            fiscal_period=f"Q{q}", metric_name="revenue",
                            metric_value=round(quarter_revenue, 2),
                        ),
                        FinancialMetric(
                            ticker=ticker, fiscal_year=fiscal_year,
                            fiscal_period=f"Q{q}", metric_name="net_income",
                            metric_value=round(quarter_profit, 2),
                        ),
                        FinancialMetric(
                            ticker=ticker, fiscal_year=fiscal_year,
                            fiscal_period=f"Q{q}", metric_name="operating_margin",
                            metric_value=round(random.uniform(0.2, 0.5), 3),
                        ),
                        FinancialMetric(
                            ticker=ticker, fiscal_year=fiscal_year,
                            fiscal_period=f"Q{q}", metric_name="eps",
                            metric_value=round(quarter_profit / random.uniform(1_000_000, 10_000_000), 2),
                        ),
                    ])

            session.add_all(metrics_data)
            await session.flush()
            total_financials += len(metrics_data)
            logger.info("  %s: %d financial metric rows", ticker, len(metrics_data))

        await session.commit()
        logger.info(
            "Market data seeded: %d prices, %d financials across %d companies",
            total_prices, total_financials, len(companies),
        )
        return total_prices + total_financials


async def main():
    await seed_market_data()


if __name__ == "__main__":
    asyncio.run(main())
