"""预设/指标 API 端点单测 — 只读查询（预设列表、指标库）+ 触发校验。"""

from __future__ import annotations

import uuid as _uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import CriteriaPreset


async def _builtin_id(db: AsyncSession, style_tag: str) -> str:
    row = (
        await db.execute(
            select(CriteriaPreset).where(CriteriaPreset.is_builtin.is_(True), CriteriaPreset.style_tag == style_tag)
        )
    ).scalar_one()
    return str(row.id)


async def test_metrics_endpoint(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/screener/metrics")
    assert resp.status_code == 200
    metrics = resp.json()["metrics"]
    keys = {m["key"] for m in metrics}
    assert {"roe", "net_margin", "market_cap"} <= keys
    roe = next(m for m in metrics if m["key"] == "roe")
    assert roe["name_cn"] and roe["category"] and roe["data_source"]


async def test_presets_list_contains_builtins(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/screener/presets")
    assert resp.status_code == 200
    tags = {p["style_tag"] for p in resp.json()["presets"] if p["is_builtin"]}
    assert tags == {
        "core", "growth", "value", "garp", "cycle",
        "financial", "bank", "insurance",
    }


async def test_trigger_presets_mode(async_client: AsyncClient, test_session: AsyncSession):
    pid = await _builtin_id(test_session, "cycle")
    resp = await async_client.post(
        "/api/v1/screener/runs",
        json={"mode": "presets", "pool": "all", "preset_ids": [pid], "combine": "union"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "presets"

    # freeform 已删除：无 body / 空 body → 422
    resp2 = await async_client.post("/api/v1/screener/runs")
    assert resp2.status_code == 422
    resp3 = await async_client.post("/api/v1/screener/runs", json={})
    assert resp3.status_code == 422


async def test_trigger_unknown_preset_422(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/screener/runs",
        json={"mode": "presets", "pool": "all", "preset_ids": [str(_uuid.uuid4())], "combine": "union"},
    )
    assert resp.status_code == 422


async def test_trigger_bad_combine_422(async_client: AsyncClient, test_session: AsyncSession):
    pid = await _builtin_id(test_session, "core")
    resp = await async_client.post(
        "/api/v1/screener/runs",
        json={"mode": "presets", "pool": "all", "preset_ids": [pid], "combine": "xor"},
    )
    assert resp.status_code == 422


async def test_trigger_empty_body_422(async_client: AsyncClient):
    """freeform 已删除：body={} → 422。"""
    resp = await async_client.post("/api/v1/screener/runs", json={})
    assert resp.status_code == 422


async def test_trigger_invalid_uuid_422(async_client: AsyncClient):
    resp = await async_client.post(
        "/api/v1/screener/runs",
        json={"mode": "presets", "pool": "all", "preset_ids": ["not-a-uuid"], "combine": "union"},
    )
    assert resp.status_code == 422
