"""财务数据定时更新任务单测 — 三类数据源调用与失败隔离。"""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core import financial_sync


@pytest.fixture
def sync_env(monkeypatch):
    calls: list[tuple[str, str]] = []

    async def _ok(db, date):
        calls.append(("ok", date))
        return 10

    monkeypatch.setattr("screener.ingest._latest_report_date", lambda: "20260630")
    monkeypatch.setattr("screener.ingest.ingest_marketwide_yjbb", _ok)
    monkeypatch.setattr("screener.ingest.ingest_marketwide_main_finance", _ok)
    monkeypatch.setattr("screener.ingest.ingest_marketwide_bs_cf", _ok)
    return calls


async def test_runs_all_families(test_session: AsyncSession, sync_env):
    result = await financial_sync.financial_data_update(db=test_session)

    assert result["report_date"] == "20260630"
    assert set(result["families"]) == {"yjbb", "main_finance", "bs_cf"}
    assert all(v == {"status": "ok", "count": 10} for v in result["families"].values())
    assert len(sync_env) == 3


async def test_failure_is_isolated(test_session: AsyncSession, monkeypatch):
    async def _fail(db, date):
        raise RuntimeError("eastmoney blocked")

    async def _ok(db, date):
        return 5

    monkeypatch.setattr("screener.ingest._latest_report_date", lambda: "20260630")
    monkeypatch.setattr("screener.ingest.ingest_marketwide_yjbb", _fail)
    monkeypatch.setattr("screener.ingest.ingest_marketwide_main_finance", _ok)
    monkeypatch.setattr("screener.ingest.ingest_marketwide_bs_cf", _ok)

    result = await financial_sync.financial_data_update(db=test_session)

    assert result["families"]["yjbb"]["status"] == "failed"
    assert "eastmoney blocked" in result["families"]["yjbb"]["error"]
    assert result["families"]["main_finance"] == {"status": "ok", "count": 5}
    assert result["families"]["bs_cf"] == {"status": "ok", "count": 5}
