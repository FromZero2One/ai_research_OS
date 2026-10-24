"""批量 upsert 单测 — 全市场灌库用一条 delete + 一次 bulk insert 替代逐 ticker 循环。"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import datetime as dt

from market.domain import FinancialMetricEntry
from market.models import FinancialMetric
from screener.ingest import upsert_metrics_batch


def _e(ticker_unused, year=2024, period="Q3", **metrics) -> dict:
    """{ticker: [entries]} 便捷构造。"""
    return [
        FinancialMetricEntry(fiscal_year=year, fiscal_period=period, metric_name=k, metric_value=v)
        for k, v in metrics.items()
    ]


class TestUpsertMetricsBatch:
    async def test_multi_ticker_insert(self, test_session: AsyncSession):
        data = {
            "600519": _e("600519", roe=26.09, gross_margin=91.5),
            "300750": _e("300750", roe=20.0),
            "000001": _e("000001", roe=11.0),
        }
        n = await upsert_metrics_batch(test_session, data)
        await test_session.flush()

        rows = (await test_session.execute(select(FinancialMetric))).scalars().all()
        assert n == 4
        assert len(rows) == 4
        by_ticker = {r.ticker for r in rows}
        assert by_ticker == {"600519", "300750", "000001"}

    async def test_idempotent_overwrite(self, test_session: AsyncSession):
        """同 ticker 同期重复批量入库 → 覆盖而非追加。"""
        first = {"600519": _e("600519", roe=20.0)}
        second = {"600519": _e("600519", roe=26.09)}
        await upsert_metrics_batch(test_session, first)
        await test_session.flush()
        await upsert_metrics_batch(test_session, second)
        await test_session.flush()

        rows = (await test_session.execute(select(FinancialMetric).where(FinancialMetric.ticker == "600519"))).scalars().all()
        assert len(rows) == 1
        assert rows[0].metric_value == 26.09

    async def test_announcement_date_persisted(self, test_session: AsyncSession):
        data = {
            "600519": [
                FinancialMetricEntry(
                    fiscal_year=2026, fiscal_period="Q2", metric_name="net_income",
                    metric_value=5e8, announcement_date=dt.date(2026, 8, 25),
                )
            ]
        }
        await upsert_metrics_batch(test_session, data)
        await test_session.flush()
        row = (
            await test_session.execute(
                select(FinancialMetric).where(FinancialMetric.ticker == "600519")
            )
        ).scalar_one()
        assert row.announcement_date == dt.date(2026, 8, 25)

    async def test_empty_data_noop(self, test_session: AsyncSession):
        assert await upsert_metrics_batch(test_session, {}) == 0

    async def test_mixed_periods_per_ticker(self, test_session: AsyncSession):
        """同一 ticker 不同期 → 两个报告期都写入。"""
        data = {
            "600519": [
                FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="roe", metric_value=26.0),
                FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q4", metric_name="roe", metric_value=28.0),
            ],
        }
        n = await upsert_metrics_batch(test_session, data)
        await test_session.flush()
        assert n == 2
        rows = (await test_session.execute(select(FinancialMetric).where(FinancialMetric.ticker == "600519"))).scalars().all()
        assert len(rows) == 2
