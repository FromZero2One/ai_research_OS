"""Screener API + 编排服务集成测试（mock akshare 快照；运行链路零 LLM）。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from screener.models import ScreenerJudgement, ScreenerRun

SPOT = [
    {"ticker": "600519", "name": "贵州茅台", "price": 1500.0, "turnover": 0.3, "market_cap": 1.88e12},
    {"ticker": "300750", "name": "宁德时代", "price": 200.0, "turnover": 1.0, "market_cap": 8.8e11},
]

QUANT_RULES = [
    {"metric": "price", "op": "<", "value": 1000.0, "missing_data_policy": "exclude"}
]


def _create_preset(qualitative=None) -> str:
    """测试专用预设：价格 < 1000（可选附加定性/事实检查条目）。"""
    import asyncio

    from sqlalchemy.ext.asyncio import AsyncSession

    from screener.models import CriteriaPreset
    from tests.conftest import test_async_engine

    async def _go():
        async with test_async_engine.connect() as conn:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            preset = CriteriaPreset(
                name="低价优质", description="价格低于 1000",
                style_tag="core", quant_rules=QUANT_RULES, qualitative=qualitative or [],
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
    """mock 全市场快照（运行链路零 LLM，无任何 LLM 桩）。"""
    monkeypatch.setattr("screener.screening.fetch_market_spot", lambda: _async(SPOT))

    # API 测试不做真实财务数据补采
    async def _no_ingest(db, needed):
        return False

    monkeypatch.setattr("screener.service._ensure_market_data", _no_ingest)


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


class TestLatestReport:
    def _clear_completed_runs(self) -> None:
        import asyncio

        from sqlalchemy import delete
        from sqlalchemy.ext.asyncio import AsyncSession

        from tests.conftest import test_async_engine

        async def _go():
            async with test_async_engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                await session.execute(delete(ScreenerRun).where(ScreenerRun.status == "completed"))
                await session.commit()
                await session.close()

        asyncio.run(_go())

    def test_latest_report_404_without_completed_run(self, client: TestClient):
        self._clear_completed_runs()
        resp = client.get("/api/v1/screener/latest-report")
        assert resp.status_code == 404

    def test_latest_report_returns_markdown(
        self, client: TestClient, screener_env, preset_payload: dict
    ):
        self._clear_completed_runs()
        resp = client.post("/api/v1/screener/runs", json=preset_payload)
        assert resp.status_code == 201
        run = _run_screener_run(client, resp.json())
        assert run["status"] == "completed"
        latest = client.get("/api/v1/screener/latest-report")
        assert latest.status_code == 200
        data = latest.json()
        assert data["run_id"] == run["id"]
        assert "推荐列表" in data["report"]


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


class TestSchedule:
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
        # 变化日报/Webhook 已退役：响应不得再含 webhook 字段
        assert "webhook" not in data

    def test_schedule_run_queues_task(self, client: TestClient):
        resp = client.post("/api/v1/screener/schedule/run")
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "queued"
        # task_manager 已退役：后台直跑协程，无持久任务 id
        assert "task_id" not in data


class TestDeterministicJudgement:
    """确定性判定（零 LLM）：fact fail → reject 且落库；报告三段结构。"""

    def _seed_financial(self, ticker: str, metric: str, value: float) -> None:
        import asyncio

        from sqlalchemy.ext.asyncio import AsyncSession

        from market.models import FinancialMetric
        from screener.service import _latest_fiscal
        from tests.conftest import test_async_engine

        _date, year, period = _latest_fiscal()

        async def _go():
            async with test_async_engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                session.add(
                    FinancialMetric(
                        ticker=ticker, metric_name=metric, metric_value=value,
                        fiscal_year=year, fiscal_period=period,
                    )
                )
                await session.commit()
                await session.close()

        asyncio.run(_go())

    def _fact_preset_payload(self) -> dict:
        pid = _create_preset(
            qualitative=[
                {"type": "fact_check", "check": "cash_coverage",
                 "threshold": 1.0, "metric": "cash_ratio"},
            ]
        )
        return {"mode": "presets", "pool": "all", "preset_ids": [pid], "combine": "union"}

    def test_fact_fail_rejects_and_persists(
        self, client: TestClient, screener_env
    ):
        self._seed_financial("300750", "cash_ratio", 0.5)  # 低于阈值 1.0 → fail
        resp = client.post("/api/v1/screener/runs", json=self._fact_preset_payload())
        assert resp.status_code == 201, resp.text
        run = _run_screener_run(client, resp.json())
        assert run["status"] == "completed"
        assert run["result_count"] == 0
        data = client.get(f"/api/v1/screener/runs/{run['id']}").json()
        assert len(data["judgements"]) == 1
        j = data["judgements"][0]
        assert j["verdict"] == "reject"
        assert j["recommend"] is False
        assert j["confidence"] is None  # confidence 已退役，列保留恒空
        assert any(h.get("check") == "cash_coverage" for h in j["criteria_hits"])

    def test_historical_run_detail_still_readable(self, client: TestClient):
        """历史 run（completed + judgements）仍可查询 — 表与 ORM 保留。"""
        import asyncio

        from sqlalchemy.ext.asyncio import AsyncSession

        from tests.conftest import test_async_engine

        async def _go():
            async with test_async_engine.connect() as conn:
                session = AsyncSession(bind=conn, expire_on_commit=False)
                run = ScreenerRun(
                    criteria_hash="legacy", criteria_text="历史运行",
                    mode="presets", preset_ids=[], combine_mode="union",
                    pool_override="all", status="completed",
                    candidate_count=1, result_count=1,
                )
                session.add(run)
                await session.flush()
                session.add(
                    ScreenerJudgement(
                        run_id=run.id, ticker="600519", name="贵州茅台",
                        recommend=True, verdict="recommend", reasons=[],
                        criteria_hits=[], confidence=1.0, snapshot={}, status="ok",
                    )
                )
                await session.commit()
                rid = str(run.id)
                await session.close()
                return rid

        rid = asyncio.run(_go())
        resp = client.get(f"/api/v1/screener/runs/{rid}")
        assert resp.status_code == 200
        assert len(resp.json()["judgements"]) == 1

    def test_report_three_sections_in_order(
        self, client: TestClient, screener_env, preset_payload: dict
    ):
        resp = client.post("/api/v1/screener/runs", json=preset_payload)
        run = _run_screener_run(client, resp.json())
        report = client.get(f"/api/v1/screener/runs/{run['id']}/report").json()["report"]
        i1 = report.index("量化筛选")
        i2 = report.index("事实检查")
        i3 = report.index("不推荐/存疑原因")
        assert i1 < i2 < i3
        assert "年报证据" not in report


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
