"""回测 Point-in-Time — 公告日晚于调仓日的财务数据不得进入该期。"""

from __future__ import annotations

import datetime as dt

from sqlalchemy.ext.asyncio import AsyncSession

from market.models import FinancialMetric
from screener.backtest_service import _load_financials_by_period


async def test_announcement_date_filters_future_data(test_session: AsyncSession):
    rows = [
        # AAA：调仓日前已公告
        ("AAA", "net_income", 5e8, dt.date(2026, 8, 20)),
        ("AAA", "total_assets", 8e9, None),  # 无公告日 → 借用同票该期公告日
        # BBB：调仓日后才公告 → 不应进入 2026-08-31 调仓
        ("BBB", "net_income", 6e8, dt.date(2026, 9, 10)),
        ("BBB", "total_assets", 9e9, None),
    ]
    for ticker, metric, value, announced in rows:
        test_session.add(
            FinancialMetric(
                ticker=ticker, fiscal_year=2026, fiscal_period="Q2",
                metric_name=metric, metric_value=value,
                announcement_date=announced,
            )
        )
    await test_session.flush()

    loaded = await _load_financials_by_period(
        test_session,
        [(2026, "Q2")],
        {(2026, "Q2"): dt.date(2026, 8, 31)},
    )
    by_ticker = loaded[(2026, "Q2")]
    assert "AAA" in by_ticker
    assert "BBB" not in by_ticker
    assert {e.metric_name for e in by_ticker["AAA"]} == {"net_income", "total_assets"}


async def test_legacy_rows_without_announcement_date_are_kept(test_session: AsyncSession):
    test_session.add(
        FinancialMetric(
            ticker="CCC", fiscal_year=2026, fiscal_period="Q2",
            metric_name="net_income", metric_value=3e8,
        )
    )
    await test_session.flush()
    loaded = await _load_financials_by_period(
        test_session, [(2026, "Q2")], {(2026, "Q2"): dt.date(2026, 1, 1)}
    )
    assert "CCC" in loaded[(2026, "Q2")]
