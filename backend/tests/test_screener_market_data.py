"""_ensure_market_data 补采决策单测（采集函数全部 mock，不触网）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

from sqlalchemy.ext.asyncio import AsyncSession

import screener.service as svc
from market.models import FinancialMetric


async def _seed(db: AsyncSession, metric: str, value: float = 1.0) -> None:
    db.add(
        FinancialMetric(
            ticker="600519",
            metric_name=metric,
            metric_value=value,
            fiscal_year=2026,
            fiscal_period="Q2",
        )
    )
    await db.flush()


class TestEnsureMarketData:
    async def test_skips_when_metric_present(self, test_session: AsyncSession, monkeypatch):
        await _seed(test_session, "current_ratio", 5.59)
        main = AsyncMock(return_value=0)
        monkeypatch.setattr("screener.ingest.ingest_marketwide_main_finance", main)

        changed = await svc._ensure_market_data(test_session, {"current_ratio"})

        assert changed is False
        main.assert_not_awaited()

    async def test_triggers_main_finance_when_missing(self, test_session: AsyncSession, monkeypatch):
        main = AsyncMock(return_value=0)
        monkeypatch.setattr("screener.ingest.ingest_marketwide_main_finance", main)

        changed = await svc._ensure_market_data(test_session, {"current_ratio"})

        assert changed is True
        main.assert_awaited_once()

    async def test_triggers_yjbb_and_bs_cf(self, test_session: AsyncSession, monkeypatch):
        yjbb = AsyncMock(return_value=0)
        bs_cf = AsyncMock(return_value=0)
        monkeypatch.setattr("screener.ingest.ingest_marketwide_yjbb", yjbb)
        monkeypatch.setattr("screener.ingest.ingest_marketwide_bs_cf", bs_cf)

        changed = await svc._ensure_market_data(test_session, {"roe", "debt_to_equity"})

        assert changed is True
        yjbb.assert_awaited_once()
        bs_cf.assert_awaited_once()

    async def test_source_failure_isolated(self, test_session: AsyncSession, monkeypatch):
        yjbb = AsyncMock(side_effect=RuntimeError("yjbb down"))
        main = AsyncMock(return_value=0)
        monkeypatch.setattr("screener.ingest.ingest_marketwide_yjbb", yjbb)
        monkeypatch.setattr("screener.ingest.ingest_marketwide_main_finance", main)

        changed = await svc._ensure_market_data(test_session, {"roe", "current_ratio"})

        assert changed is True  # yjbb 失败，但 F10 仍补采成功
        yjbb.assert_awaited_once()
        main.assert_awaited_once()
