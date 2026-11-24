"""Screener API + 编排服务集成测试（mock akshare 快照与 LLM）。"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from core.interfaces import LLMResponse

SPOT = [
    {"ticker": "600519", "name": "贵州茅台", "price": 1500.0, "turnover": 0.3, "market_cap": 1.88e12},
    {"ticker": "300750", "name": "宁德时代", "price": 200.0, "turnover": 1.0, "market_cap": 8.8e11},
]

QUANT_RULES = [
    {"metric": "price", "op": "<", "value": 1000.0, "missing_data_policy": "exclude"}
]

VALID_JUDGE = {
    "recommend": True,
    "reasons": ["符合标准"],
    "criteria_hits": [{"criterion": "现金充裕", "hit": True, "evidence": "流动比率 4.0 倍"}],
    "confidence": 0.8,
}


class FakeLLM:
    async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            content=f"```json\n{json.dumps(VALID_JUDGE, ensure_ascii=False)}\n```",
            model="fake", usage=None,
        )


def _create_preset() -> str:
    """测试专用预设：价格 < 1000 + 定性「现金充裕」。"""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    from screener.models import CriteriaPreset
    from tests.conftest import test_async_engine

    async def _go():
        async with test_async_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            preset = CriteriaPreset(
                name="低价优质", description="价格低于 1000 且现金充裕",
                style_tag="core", quant_rules=QUANT_RULES, qualitative=["现金充裕"],
            )
            session.add(preset)
            await session.commit()
            pid = str(preset.id)
            await session.close()
            return pid

    return asyncio.run(_go())


@pytest.fixture
def preset_payload() -> dict:
    """presets 模式触发 body（唯一合法入口）。"""
    return {
        "mode": "presets", "pool": "all",
        "preset_ids": [_create_preset()], "combine": "union",
    }


@pytest.fixture
def screener_env(monkeypatch):
    """mock 全市场快照 + LLM 创建。"""
    monkeypatch.setattr("screener.screening.fetch_market_spot", lambda: _async(SPOT))
    monkeypatch.setattr("screener.service.create_llm", lambda: FakeLLM())

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
    def test_full_run(self, client: TestClient, screener_env, preset_payload: dict):
        resp = client.post("/api/v1/screener/runs", json=preset_payload)
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

    def test_trigger_then_immediate_get(
        self, client: TestClient, screener_env, preset_payload: dict
    ):
        """POST 返回后立即按 id 查询必须可见（run 行已在返回前提交）。"""
        resp = client.post("/api/v1/screener/runs", json=preset_payload)
        assert resp.status_code == 201, resp.text
        run_id = resp.json()["id"]
        detail = client.get(f"/api/v1/screener/runs/{run_id}")
        assert detail.status_code == 200
        assert detail.json()["id"] == run_id

    def test_duplicate_trigger_409(self, client: TestClient, screener_env, preset_payload: dict):
        first = client.post("/api/v1/screener/runs", json=preset_payload)
        assert first.status_code == 201
        # run 仍是 pending（未执行）→ 再次触发应 409
        second = client.post("/api/v1/screener/runs", json=preset_payload)
        assert second.status_code == 409


class TestExportAndSchedule:
    def test_export_csv(self, client: TestClient, screener_env, preset_payload: dict):
        resp = client.post("/api/v1/screener/runs", json=preset_payload)
        run = _run_screener_run(client, resp.json())
        resp = client.get(f"/api/v1/screener/runs/{run['id']}/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        text = resp.content.decode("utf-8-sig")
        assert text.startswith("代码,名称,结论,推荐")
        assert "300750" in text and "宁德时代" in text

    def test_push_recommendation_to_watchlist(
        self, client: TestClient, screener_env, preset_payload: dict
    ):
        company = client.post(
            "/api/v1/companies",
            json={"ticker": "300750", "name": "宁德时代"},
        ).json()
        client.patch(
            f"/api/v1/companies/{company['id']}", json={"is_active": False}
        )
        trigger = client.post("/api/v1/screener/runs", json=preset_payload)
        run = _run_screener_run(client, trigger.json())

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

    def test_diff_with_explicit_base(
        self, client: TestClient, screener_env, preset_payload: dict
    ):
        first_resp = client.post("/api/v1/screener/runs", json=preset_payload)
        first = _run_screener_run(client, first_resp.json())
        second_resp = client.post("/api/v1/screener/runs", json=preset_payload)
        second = _run_screener_run(client, second_resp.json())
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

    def test_data_quality(self, client: TestClient):
        resp = client.get("/api/v1/screener/data-quality")
        assert resp.status_code == 200
        data = resp.json()
        assert "financial" in data and "prices" in data and "knowledge" in data
        assert isinstance(data["warnings"], list)
        # 测试库被清空 → 财务库为空，应给出告警
        assert data["financial"]["period"] is None
        assert any("财务" in w for w in data["warnings"])

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


class TestTriggerValidation:
    def test_empty_body_422(self, client: TestClient):
        """freeform 已删除：无 body / 空 body → 路由层 422。"""
        assert client.post("/api/v1/screener/runs").status_code == 422
        assert client.post("/api/v1/screener/runs", json={}).status_code == 422

    def test_freeform_mode_422(self, client: TestClient):
        resp = client.post(
            "/api/v1/screener/runs", json={"mode": "freeform", "preset_ids": ["x"]}
        )
        assert resp.status_code == 422


class TestRunsList:
    def test_list_runs(self, client: TestClient):
        resp = client.get("/api/v1/screener/runs")
        assert resp.status_code == 200
        assert isinstance(resp.json()["runs"], list)
