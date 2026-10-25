"""预补全回测所需 9 个报告期的财务数据（含 F10 指标），再验证完整性。"""

import asyncio

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from screener.backtest_data import ensure_financial_periods

PERIODS = [
    (2023, "Q3"),
    (2023, "Q4"),
    (2024, "Q2"),
    (2024, "Q3"),
    (2024, "Q4"),
    (2025, "Q2"),
    (2025, "Q3"),
    (2025, "Q4"),
    (2026, "Q2"),
]

REQUIRED = ("eps", "total_assets", "operating_cash_flow")
F10_MARKERS = ("roic", "fcff", "current_ratio")


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        n = await ensure_financial_periods(db, PERIODS)
        await db.commit()
        print("本次补拉期数:", n, flush=True)

        from sqlalchemy import select

        from market.models import FinancialMetric

        for year, period in PERIODS:
            rows = (
                (
                    await db.execute(
                        select(FinancialMetric.metric_name)
                        .where(
                            FinancialMetric.fiscal_year == year,
                            FinancialMetric.fiscal_period == period,
                        )
                        .distinct()
                    )
                )
                .scalars()
                .all()
            )
            names = set(rows)
            ok = all(m in names for m in REQUIRED) and any(m in names for m in F10_MARKERS)
            missing = [m for m in REQUIRED if m not in names]
            f10 = [m for m in F10_MARKERS if m not in names]
            print(
                f"{year}{period}: 指标{len(names)}种 完整={ok} 缺={missing} F10缺={f10}", flush=True
            )
    await engine.dispose()


asyncio.run(main())
