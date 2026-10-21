"""ingest 编排单测（mock 拉取函数）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from market.models import FinancialMetric
from screener.ingest import ingest_marketwide_yjbb, ingest_single_company


class TestIngestMarketwideYjbb:
    async def test_bulk_ingest(self, test_session: AsyncSession, monkeypatch):
        raw = [
            {"股票代码": "600519", "净资产收益率": 26.09, "销售毛利率": 91.5,
             "营业总收入-营业总收入": 1.2e11, "净利润-净利润": 6.0e10},
            {"股票代码": "000001", "净资产收益率": 11.0, "销售毛利率": None,
             "营业总收入-营业总收入": 1.0e11, "净利润-净利润": 1.1e10},
        ]
        monkeypatch.setattr("screener.ingest.fetch_yjbb_raw", AsyncMock(return_value=raw))
        n = await ingest_marketwide_yjbb(test_session, date="20240930")
        await test_session.flush()

        assert n == 2
        rows = (await test_session.execute(select(FinancialMetric))).scalars().all()
        tickers = {r.ticker for r in rows}
        assert tickers == {"600519", "000001"}
        moutai_roe = next(r for r in rows if r.ticker == "600519" and r.metric_name == "roe")
        assert moutai_roe.metric_value == 26.09

    async def test_bad_ticker_rows_skipped(self, test_session: AsyncSession, monkeypatch):
        raw = [
            {"股票代码": None, "净资产收益率": 10.0},
            {"股票代码": "600519", "净资产收益率": 26.09},
        ]
        monkeypatch.setattr("screener.ingest.fetch_yjbb_raw", AsyncMock(return_value=raw))
        n = await ingest_marketwide_yjbb(test_session, date="20240930")
        assert n == 1


class TestIngestSingleCompany:
    async def test_bs_and_cf(self, test_session: AsyncSession, monkeypatch):
        async def fake_bs(ticker):
            return {
                "REPORT_DATE": "2024-06-30 00:00:00",
                "TOTAL_ASSETS": 3000.0, "TOTAL_LIABILITIES": 1000.0, "TOTAL_EQUITY": 2000.0,
                "CURRENT_ASSET_BALANCE": 1500.0, "CURRENT_LIAB_BALANCE": 1000.0,
            }

        async def fake_cf(ticker):
            return {"REPORT_DATE": "2024-06-30 00:00:00", "NETCASH_OPERATE": 5.0e10}

        monkeypatch.setattr("screener.ingest.fetch_balance_sheet_raw", fake_bs)
        monkeypatch.setattr("screener.ingest.fetch_cash_flow_raw", fake_cf)

        n = await ingest_single_company(test_session, "600519")
        await test_session.flush()

        rows = (await test_session.execute(select(FinancialMetric).where(FinancialMetric.ticker == "600519"))).scalars().all()
        names = {r.metric_name for r in rows}
        assert n == 5  # total_assets / total_liabilities / debt_to_equity / current_ratio / operating_cash_flow
        assert {"total_assets", "total_liabilities", "debt_to_equity", "current_ratio", "operating_cash_flow"} <= names

    async def test_bs_failure_isolated(self, test_session: AsyncSession, monkeypatch):
        """bs 拉取失败不阻塞 cf。"""
        async def boom_bs(ticker):
            raise RuntimeError("bs 接口挂了")

        async def ok_cf(ticker):
            return {"REPORT_DATE": "2024-06-30 00:00:00", "NETCASH_OPERATE": 5.0e10}

        monkeypatch.setattr("screener.ingest.fetch_balance_sheet_raw", boom_bs)
        monkeypatch.setattr("screener.ingest.fetch_cash_flow_raw", ok_cf)

        n = await ingest_single_company(test_session, "600519")
        assert n == 1  # 只有 operating_cash_flow
