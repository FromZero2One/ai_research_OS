"""ingest 服务层单测（mock 子进程 + 内存库）。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from market.models import FinancialMetric
from screener.ingest import fetch_main_finance_raw, fetch_yjbb_raw, upsert_metrics


class TestFetchYjbbRaw:
    async def test_parses_child_output(self, monkeypatch):
        sample = [{"股票代码": "600519", "净资产收益率": 26.09}]
        monkeypatch.setattr(
            "screener.ingest._run_child",
            lambda code, timeout=180: sample,
        )
        rows = await fetch_yjbb_raw("20240930")
        assert rows == sample

    async def test_child_failure_raises(self, monkeypatch):
        def _boom(code, timeout=180):
            raise RuntimeError("子进程失败")

        monkeypatch.setattr("screener.ingest._run_child", _boom)
        with pytest.raises(RuntimeError):
            await fetch_yjbb_raw("20240930")


class TestFetchMainFinanceRaw:
    async def test_passes_report_date_filter(self, monkeypatch):
        captured: dict[str, str] = {}

        def fake_child(code, timeout=180):
            captured["code"] = code
            return [{"SECURITY_CODE": "600519"}]

        monkeypatch.setattr("screener.ingest._run_child", fake_child)
        rows = await fetch_main_finance_raw("20260630")
        assert rows == [{"SECURITY_CODE": "600519"}]
        assert "2026-06-30" in captured["code"]


class TestParseMainFinanceRow:
    def test_maps_all_missing_metrics(self):
        from screener.ingest import parse_main_finance_row

        row = {
            "EPSJB": 35.57,
            "LD": 5.59,
            "SD": 4.27,
            "TOAZZL": 0.30,
            "CHZZL": 0.15,
            "YSZKZZL": 100.0,
            "TOTALOPERATEREVETZ": 1.30,
            "PARENTNETPROFITTZ": -1.95,
        }
        entries = {e.metric_name: e.metric_value for e in parse_main_finance_row(row, 2026, "Q2")}
        assert entries == {
            "eps": 35.57,
            "current_ratio": 5.59,
            "quick_ratio": 4.27,
            "asset_turnover": 0.30,
            "inventory_turnover": 0.15,
            "receivables_turnover": 100.0,
            "revenue_growth": 1.30,
            "net_income_growth": -1.95,
        }

    def test_missing_values_skipped(self):
        from screener.ingest import parse_main_finance_row

        assert parse_main_finance_row({"LD": None, "SECURITY_CODE": "600519"}, 2026, "Q2") == []


class TestUpsertMetrics:
    async def test_insert_and_dedup(self, test_session: AsyncSession):
        from market.domain import FinancialMetricEntry

        entries = [
            FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="roe", metric_value=26.09),
            FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="roe", metric_value=26.09),  # 重复
            FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="gross_margin", metric_value=91.5),
        ]
        n = await upsert_metrics(test_session, "600519", entries)
        await test_session.flush()

        rows = (await test_session.execute(select(FinancialMetric).where(FinancialMetric.ticker == "600519"))).scalars().all()
        assert n == 2  # 重复的 roe 去重
        assert len(rows) == 2
        by_metric = {r.metric_name: r for r in rows}
        assert by_metric["roe"].metric_value == 26.09
        assert by_metric["roe"].metric_unit == "%"

    async def test_second_call_replaces_old_period(self, test_session: AsyncSession):
        """同 ticker 同期重复入库 → 更新而非追加（幂等）。"""
        from market.domain import FinancialMetricEntry

        e1 = [FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="roe", metric_value=20.0)]
        e2 = [FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="roe", metric_value=26.09)]
        await upsert_metrics(test_session, "600519", e1)
        await test_session.flush()
        await upsert_metrics(test_session, "600519", e2)
        await test_session.flush()

        rows = (await test_session.execute(select(FinancialMetric).where(FinancialMetric.ticker == "600519"))).scalars().all()
        assert len(rows) == 1
        assert rows[0].metric_value == 26.09

    async def test_unit_assignment(self, test_session: AsyncSession):
        """百分比指标 → '%'，金额指标 → '元'，比率 → '倍'。"""
        from market.domain import FinancialMetricEntry

        entries = [
            FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="roe", metric_value=26.0),
            FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="revenue", metric_value=1e11),
            FinancialMetricEntry(fiscal_year=2024, fiscal_period="Q3", metric_name="current_ratio", metric_value=1.5),
        ]
        await upsert_metrics(test_session, "000001", entries)
        await test_session.flush()

        rows = (await test_session.execute(select(FinancialMetric).where(FinancialMetric.ticker == "000001"))).scalars().all()
        by_metric = {r.metric_name: r.metric_unit for r in rows}
        assert by_metric["roe"] == "%"
        assert by_metric["revenue"] == "元"
        assert by_metric["current_ratio"] == "倍"
