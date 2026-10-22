"""ingest 编排单测（mock 拉取函数）。"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from market.models import FinancialMetric
from screener.ingest import (
    ingest_marketwide_bs_cf,
    ingest_marketwide_main_finance,
    ingest_marketwide_yjbb,
    ingest_single_company,
)


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

    async def test_eps_and_growth_fields_mapped(self, test_session: AsyncSession, monkeypatch):
        raw = [{
            "股票代码": "600519",
            "每股收益": 35.57,
            "营业总收入-同比增长": 1.30,
            "净利润-同比增长": -1.95,
        }]
        monkeypatch.setattr("screener.ingest.fetch_yjbb_raw", AsyncMock(return_value=raw))
        await ingest_marketwide_yjbb(test_session, date="20260630")
        await test_session.flush()

        rows = (await test_session.execute(
            select(FinancialMetric).where(FinancialMetric.ticker == "600519")
        )).scalars().all()
        by_metric = {r.metric_name: r.metric_value for r in rows}
        assert by_metric["eps"] == 35.57
        assert by_metric["revenue_growth"] == 1.30
        assert by_metric["net_income_growth"] == -1.95


class TestIngestMarketwideMainFinance:
    async def test_maps_ratios_and_filters_non_a_share(
        self, test_session: AsyncSession, monkeypatch
    ):
        raw = [
            {
                "SECURITY_CODE": "600519",
                "REPORT_DATE": "2026-06-30 00:00:00",
                "LD": 5.59,
                "SD": 4.27,
                "EPSJB": 35.57,
                "TOAZZL": 0.30,
                "CHZZL": 0.15,
                "YSZKZZL": 100.0,
                "TOTALOPERATEREVETZ": 1.30,
                "PARENTNETPROFITTZ": -1.95,
            },
            # 新三板 83 前缀：应在入库前被过滤
            {"SECURITY_CODE": "873283", "REPORT_DATE": "2026-06-30 00:00:00", "LD": 3.6},
        ]
        monkeypatch.setattr("screener.ingest.fetch_main_finance_raw", AsyncMock(return_value=raw))

        n = await ingest_marketwide_main_finance(test_session, date="20260630")
        await test_session.flush()

        assert n == 1
        rows = (await test_session.execute(select(FinancialMetric))).scalars().all()
        assert {r.ticker for r in rows} == {"600519"}
        by_metric = {r.metric_name: r.metric_value for r in rows}
        assert by_metric["current_ratio"] == 5.59
        assert by_metric["quick_ratio"] == 4.27
        assert by_metric["asset_turnover"] == 0.30
        assert by_metric["inventory_turnover"] == 0.15
        assert by_metric["receivables_turnover"] == 100.0
        assert by_metric["eps"] == 35.57
        assert by_metric["revenue_growth"] == 1.30
        assert by_metric["net_income_growth"] == -1.95


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


class TestParseZcfzRow:
    """全市场资产负债表行解析（stock_zcfz_em 列）。"""

    def test_full_row(self):
        from screener.ingest import parse_zcfz_row

        row = {
            "股票代码": "600519",
            "资产-总资产": 3.0e11,
            "负债-总负债": 5.0e10,
            "股东权益合计": 2.5e11,
            "资产负债率": 16.41,
        }
        entries = {e.metric_name: e.metric_value for e in parse_zcfz_row(row, 2025, "Q4")}
        assert entries["total_assets"] == 3.0e11
        assert entries["total_liabilities"] == 5.0e10
        assert entries["debt_to_equity"] == pytest.approx(5.0e10 / 2.5e11 * 100)

    def test_missing_values_skipped(self):
        from screener.ingest import parse_zcfz_row

        row = {"股票代码": "600519", "资产-总资产": None, "负债-总负债": None}
        assert parse_zcfz_row(row, 2025, "Q4") == []


class TestParseXjllRow:
    """全市场现金流量表行解析（stock_xjll_em 列）。"""

    def test_full_row(self):
        from screener.ingest import parse_xjll_row

        row = {"股票代码": "600519", "经营性现金流-现金流量净额": 9.2e10}
        entries = parse_xjll_row(row, 2025, "Q4")
        assert len(entries) == 1
        assert entries[0].metric_name == "operating_cash_flow"
        assert entries[0].metric_value == 9.2e10

    def test_missing_value_skipped(self):
        from screener.ingest import parse_xjll_row

        assert parse_xjll_row({"股票代码": "600519"}, 2025, "Q4") == []


class TestIngestMarketwideBsCf:
    async def test_bulk_ingest(self, test_session: AsyncSession, monkeypatch):
        zcfz = [
            {"股票代码": "600519", "资产-总资产": 3.0e11, "负债-总负债": 5.0e10, "股东权益合计": 2.5e11},
            {"股票代码": "000001", "资产-总资产": None, "负债-总负债": None},
        ]
        xjll = [{"股票代码": "600519", "经营性现金流-现金流量净额": 9.2e10}]
        monkeypatch.setattr("screener.ingest.fetch_zcfz_raw", AsyncMock(return_value=zcfz))
        monkeypatch.setattr("screener.ingest.fetch_xjll_raw", AsyncMock(return_value=xjll))

        n = await ingest_marketwide_bs_cf(test_session, date="20250930")
        await test_session.flush()

        assert n == 2  # 600519 有 bs+cf 指标；000001 全空跳过
        rows = (await test_session.execute(select(FinancialMetric).where(FinancialMetric.ticker == "600519"))).scalars().all()
        names = {r.metric_name for r in rows}
        assert {"total_assets", "total_liabilities", "debt_to_equity", "operating_cash_flow"} <= names

    async def test_zcfz_failure_does_not_block_xjll(self, test_session: AsyncSession, monkeypatch):
        async def boom(db, date):
            raise RuntimeError("zcfz 接口挂了")

        monkeypatch.setattr("screener.ingest.ingest_marketwide_zcfz", boom)
        monkeypatch.setattr("screener.ingest.fetch_xjll_raw", AsyncMock(
            return_value=[{"股票代码": "600519", "经营性现金流-现金流量净额": 9.2e10}]))

        n = await ingest_marketwide_bs_cf(test_session, date="20250930")
        assert n == 1


class TestIngestMarketwideCurrentRatio:
    """datacenter CURRENT_RATIO = 流动比率 × 100（茅台 509.00 ↔ 真实 5.09 验证）。"""

    async def test_current_ratio_from_zcfz(self, test_session: AsyncSession, monkeypatch):
        zcfz = [{"股票代码": "600519", "资产-总资产": 3.0e11, "负债-总负债": 5.0e10,
                 "股东权益合计": 2.5e11, "CURRENT_RATIO": 509.00}]
        xjll: list[dict] = []
        monkeypatch.setattr("screener.ingest.fetch_zcfz_raw", AsyncMock(return_value=zcfz))
        monkeypatch.setattr("screener.ingest.fetch_xjll_raw", AsyncMock(return_value=xjll))

        await ingest_marketwide_bs_cf(test_session, date="20250930")
        await test_session.flush()

        rows = (await test_session.execute(
            select(FinancialMetric).where(
                FinancialMetric.ticker == "600519",
                FinancialMetric.metric_name == "current_ratio",
            ))).scalars().all()
        assert len(rows) == 1
        assert rows[0].metric_value == pytest.approx(5.09)
