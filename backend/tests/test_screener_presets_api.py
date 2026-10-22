"""预设/指标 API 端点单测 — CRUD、内置保护 409、触发 422。"""

from __future__ import annotations

import uuid as _uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import CriteriaPreset

_VALID = {
    "name": "我的 API 预设",
    "description": "接口自建",
    "style_tag": "custom",
    "quant_rules": [{"metric": "roe", "op": ">", "value": 10, "missing_data_policy": "exclude"}],
    "qualitative": ["现金流稳定"],
    "suggested_pool": "main",
}


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
    assert tags == {"core", "growth", "value", "garp", "cycle"}


async def test_preset_create_and_delete(async_client: AsyncClient):
    resp = await async_client.post("/api/v1/screener/presets", json=_VALID)
    assert resp.status_code == 201, resp.text
    pid = resp.json()["id"]

    # 更新自建预设
    resp = await async_client.put(f"/api/v1/screener/presets/{pid}", json={"name": "改名"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "改名"

    # 删除自建预设
    resp = await async_client.delete(f"/api/v1/screener/presets/{pid}")
    assert resp.status_code == 200


async def test_preset_create_invalid_rule_422(async_client: AsyncClient):
    bad = {**_VALID, "quant_rules": [{"metric": "roe", "op": "~", "value": 1, "missing_data_policy": "exclude"}]}
    resp = await async_client.post("/api/v1/screener/presets", json=bad)
    assert resp.status_code == 422


async def test_preset_update_builtin_409(async_client: AsyncClient, test_session: AsyncSession):
    pid = await _builtin_id(test_session, "core")
    resp = await async_client.put(f"/api/v1/screener/presets/{pid}", json={"name": "改内置"})
    assert resp.status_code == 409
    resp = await async_client.delete(f"/api/v1/screener/presets/{pid}")
    assert resp.status_code == 409


async def test_trigger_presets_mode(async_client: AsyncClient, test_session: AsyncSession):
    pid = await _builtin_id(test_session, "cycle")
    resp = await async_client.post(
        "/api/v1/screener/runs",
        json={"mode": "presets", "pool": "all", "preset_ids": [pid], "combine": "union"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["mode"] == "presets"

    # 无 body → v1 自由文本（需要 criteria.md 存在）
    resp2 = await async_client.post("/api/v1/screener/runs")
    # 已有进行中的 run → 409 也是合法结果；二者均不应 500
    assert resp2.status_code in {201, 409}


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
