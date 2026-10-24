"""Screener API + 编排服务集成测试（mock akshare 快照与 LLM）。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from core.interfaces import LLMResponse
from screener.models import ScreenerRun

SPOT = [
    {"ticker": "600519", "name": "贵州茅台", "price": 1500.0, "turnover": 0.3, "market_cap": 1.88e12},
    {"ticker": "300750", "name": "宁德时代", "price": 200.0, "turnover": 1.0, "market_cap": 8.8e11},
]

RULES = {
    "stock_pool": {"type": "all", "tickers": []},
    "quant_rules": [{"metric": "price", "op": "<", "value": 1000.0, "missing_data_policy": "exclude"}],
    "qualitative_criteria": ["现金充裕"],
    "candidate_limit": 50,
}

VALID_JUDGE = {
    "recommend": True,
    "reasons": ["符合标准"],
    "criteria_hits": [{"criterion": "现金充裕", "hit": True, "evidence": "流动比率 4.0 倍"}],
    "confidence": 0.8,
}


class FakeLLM:
    async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
        last = messages[-1].content
        if "选股标准文档" in last or "标准文档" in last:
            return LLMResponse(content=f"```json\n{json.dumps(RULES, ensure_ascii=False)}\n```", model="fake", usage=None)
        return LLMResponse(content=f"```json\n{json.dumps(VALID_JUDGE, ensure_ascii=False)}\n```", model="fake", usage=None)


@pytest.fixture
def screener_env(monkeypatch):
    """mock 全市场快照 + LLM 创建。"""
    monkeypatch.setattr("screener.screening.fetch_market_spot", lambda: _async(SPOT))
    monkeypatch.setattr("screener.service.create_llm", lambda: FakeLLM())
    monkeypatch.setattr("screener.translate.create_llm", lambda: FakeLLM())

    # API 测试不做真实财务数据补采
    async def _no_ingest(db, needed):
        return False

    monkeypatch.setattr("screener.service._ensure_market_data", _no_ingest)

    class _NoKnowledge:
        async def search(self, *args, **kwargs):
            return []

    monkeypatch.setattr("screener.service._create_knowledge", lambda db: _NoKnowledge())


def _async(value):
    import asyncio

    future = asyncio.get_event_loop().create_future() if False else None
    # 简单 awaitable 包装
    class _A:
        def __await__(self):
            if False:
                yield
            return value

    return _A()


def _run_screener_run(client: TestClient, resp_json: dict) -> dict:
    """触发后直接执行 run_screener（测试环境 worker 不运行；用测试库 session）。"""
    import asyncio
    import uuid as _uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from screener.service import run_screener
    from tests.conftest import test_async_engine

    async def _go():
        async with test_async_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            run = await run_screener(session, _uuid.UUID(resp_json["id"]))
            await session.commit()
            await session.close()
            return run

    asyncio.run(_go())
    return client.get(f"/api/v1/screener/runs/{resp_json['id']}").json()


class TestTriggerAndRun:
    def test_full_run(self, client: TestClient, screener_env):
        resp = client.post("/api/v1/screener/runs")
        assert resp.status_code == 201, resp.text
        run = _run_screener_run(client, resp.json())
        assert run["status"] == "completed"
        assert run["candidate_count"] == 1  # 只有两只，价格<1000 的只有宁德时代
        assert run["result_count"] == 1
        assert run["report_path"]

        # judgement 落库
        data = client.get(f"/api/v1/screener/runs/{run['id']}").json()
        assert len(data["judgements"]) == 1
        assert data["judgements"][0]["recommend"] is True

        # 报告可读
        report = client.get(f"/api/v1/screener/runs/{run['id']}/report")
        assert report.status_code == 200
        assert "推荐列表" in report.json()["report"]

    def test_trigger_then_immediate_get(self, client: TestClient, screener_env):
        """POST 返回后立即按 id 查询必须可见（run 行已在返回前提交）。"""
        resp = client.post("/api/v1/screener/runs")
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["id"]
        detail = client.get(f"/api/v1/screener/runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == run_id

    def test_duplicate_trigger_409(self, client: TestClient, screener_env):
        first = client.post("/api/v1/screener/runs")
        assert first.status_code == 201
        # run 仍是 pending（未执行）→ 再次触发应 409
        second = client.post("/api/v1/screener/runs")
        assert second.status_code == 409

    def test_cancel_pending_run(self, client: TestClient, screener_env):
        run_id = client.post("/api/v1/screener/runs").json()["id"]
        resp = client.post(f"/api/v1/screener/runs/{run_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelling"
        # 重复取消幂等
        again = client.post(f"/api/v1/screener/runs/{run_id}/cancel")
        assert again.status_code == 200
        assert again.json()["status"] == "cancelling"

    def test_cancel_finished_run_409(self, client: TestClient, screener_env):
        resp = client.post("/api/v1/screener/runs")
        run = _run_screener_run(client, resp.json())
        cancelled = client.post(f"/api/v1/screener/runs/{run['id']}/cancel")
        assert cancelled.status_code == 409

    def test_cancel_unknown_run_404(self, client: TestClient):
        resp = client.post(
            "/api/v1/screener/runs/00000000-0000-0000-0000-000000000000/cancel"
        )
        assert resp.status_code == 404


class TestExportAndSchedule:
    def test_export_csv(self, client: TestClient, screener_env):
        run = _run_screener_run(client, client.post("/api/v1/screener/runs").json())
        resp = client.get(f"/api/v1/screener/runs/{run['id']}/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        text = resp.content.decode("utf-8-sig")
        assert text.startswith("代码,名称,结论,推荐")
        assert "300750" in text and "宁德时代" in text

    def test_push_recommendation_to_watchlist(self, client: TestClient, screener_env):
        company = client.post(
            "/api/v1/companies",
            json={"ticker": "300750", "name": "宁德时代"},
        ).json()
        client.patch(
            f"/api/v1/companies/{company['id']}", json={"is_active": False}
        )
        run = _run_screener_run(client, client.post("/api/v1/screener/runs").json())

        resp = client.post(
            f"/api/v1/screener/runs/{run['id']}/watchlist",
            json={"tickers": ["300750"]},
        )
        assert resp.status_code == 200, resp.text
        assert [x["ticker"] for x in resp.json()["added"]] == ["300750"]
        again = client.post(
            f"/api/v1/screener/runs/{run['id']}/watchlist",
            json={"tickers": ["300750"]},
        )
        assert again.json()["added"] == []
        assert [x["ticker"] for x in again.json()["already"]] == ["300750"]

    def test_diff_with_explicit_base(self, client: TestClient, screener_env):
        first = _run_screener_run(client, client.post("/api/v1/screener/runs").json())
        second = _run_screener_run(client, client.post("/api/v1/screener/runs").json())
        resp = client.get(
            f"/api/v1/screener/runs/{second['id']}/diff",
            params={"base_run_id": first["id"]},
        )
        assert resp.status_code == 200
        assert resp.json()["has_previous"] is True
        assert resp.json()["base_run_id"] == first["id"]
        # 基线与当前相同 → 422
        bad = client.get(
            f"/api/v1/screener/runs/{second['id']}/diff",
            params={"base_run_id": second["id"]},
        )
        assert bad.status_code == 422

    def test_schedule_status(self, client: TestClient):
        resp = client.get("/api/v1/screener/schedule")
        assert resp.status_code == 200
        data = resp.json()
        assert "schedule" in data and "presets" in data
        assert "enabled" in data["webhook"]

    def test_schedule_run_queues_task(self, client: TestClient):
        resp = client.post("/api/v1/screener/schedule/run")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        assert data["task_id"]


class TestSavedPortfolios:
    @staticmethod
    def _body(**overrides) -> dict:
        body = {
            "capital": 1_000_000,
            "method": "equal",
            "max_weight": 0.2,
            "max_industry_weight": 0.5,
            "max_holdings": 10,
        }
        body.update(overrides)
        return body

    def test_save_list_get_delete(self, client: TestClient, screener_env):
        run = _run_screener_run(client, client.post("/api/v1/screener/runs").json())
        resp = client.post(
            f"/api/v1/screener/runs/{run['id']}/portfolio",
            json=self._body(save=True, name="测试组合"),
        )
        assert resp.status_code == 200, resp.text
        saved = resp.json()
        assert saved["portfolio_id"]
        assert saved["name"] == "测试组合"
        portfolio_id = saved["portfolio_id"]

        listed = client.get(f"/api/v1/screener/runs/{run['id']}/portfolios")
        assert listed.status_code == 200
        rows = listed.json()["portfolios"]
        assert len(rows) == 1
        assert rows[0]["id"] == portfolio_id
        assert rows[0]["result"]["holdings"]

        detail = client.get(f"/api/v1/screener/portfolios/{portfolio_id}")
        assert detail.status_code == 200
        assert detail.json()["params"]["capital"] == 1_000_000

        assert client.get("/api/v1/screener/portfolios").status_code == 200
        deleted = client.delete(f"/api/v1/screener/portfolios/{portfolio_id}")
        assert deleted.status_code == 204
        assert client.get(f"/api/v1/screener/portfolios/{portfolio_id}").status_code == 404

    def test_compute_without_save_not_persisted(self, client: TestClient, screener_env):
        run = _run_screener_run(client, client.post("/api/v1/screener/runs").json())
        resp = client.post(
            f"/api/v1/screener/runs/{run['id']}/portfolio", json=self._body()
        )
        assert resp.status_code == 200
        assert "portfolio_id" not in resp.json()
        listed = client.get(f"/api/v1/screener/runs/{run['id']}/portfolios").json()
        assert listed["portfolios"] == []


class TestCriteriaEndpoints:
    def test_get_criteria(self, client: TestClient):
        resp = client.get("/api/v1/screener/criteria")
        assert resp.status_code == 200
        assert "股票池" in resp.json()["criteria"]

    def test_put_and_get(self, client: TestClient):
        new_text = "# 我的标准\n股票池：创业板\nROE > 20"
        put = client.put("/api/v1/screener/criteria", json={"criteria": new_text})
        assert put.status_code == 200
        assert client.get("/api/v1/screener/criteria").json()["criteria"] == new_text


class TestRunsList:
    def test_list_runs(self, client: TestClient):
        resp = client.get("/api/v1/screener/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json()["runs"], list)
