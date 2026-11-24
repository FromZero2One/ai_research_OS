"""Screener 预设 API — 预设 CRUD 与指标定义库。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.exceptions import NotFoundError
from screener.models import CriteriaPreset
from screener.presets import (
    BuiltinPresetError,
    create_preset,
    delete_preset,
    list_metrics,
    list_presets,
    update_preset,
)

router = APIRouter(tags=["Screener"])


class PresetUpsert(BaseModel):
    name: str | None = None
    description: str | None = None
    style_tag: str | None = None
    quant_rules: list[dict] | None = None
    qualitative: list[str] | None = None
    suggested_pool: str | None = None
    is_active: bool | None = None


def _preset_json(p: CriteriaPreset) -> dict:
    return {
        "id": str(p.id), "name": p.name, "description": p.description,
        "style_tag": p.style_tag, "quant_rules": p.quant_rules,
        "qualitative": p.qualitative, "suggested_pool": p.suggested_pool,
        "is_builtin": p.is_builtin, "is_active": p.is_active,
    }


@router.get("/metrics")
async def get_metrics(db: AsyncSession = Depends(get_db)):
    """指标定义库（按 category, key 排序，前端按分类分组）。"""
    metrics = await list_metrics(db)
    return {"metrics": [
        {"key": m.key, "name_cn": m.name_cn, "category": m.category,
         "data_source": m.data_source, "description": m.description}
        for m in metrics
    ]}


@router.get("/presets")
async def get_presets(include_inactive: bool = False, db: AsyncSession = Depends(get_db)):
    """预设列表（内置 + 自建）。"""
    presets = await list_presets(db, include_inactive=include_inactive)
    return {"presets": [_preset_json(p) for p in presets]}


@router.post("/presets", status_code=201)
async def post_preset(data: PresetUpsert, db: AsyncSession = Depends(get_db)):
    """新建用户预设。校验失败 → 422。"""
    try:
        preset = await create_preset(db, data.model_dump(exclude_none=True))
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    return _preset_json(preset)


@router.put("/presets/{preset_id}")
async def put_preset(preset_id: uuid.UUID, data: PresetUpsert, db: AsyncSession = Depends(get_db)):
    """更新预设；内置预设 → 409（复制后编辑）。"""
    try:
        preset = await update_preset(db, preset_id, data.model_dump(exclude_none=True))
    except BuiltinPresetError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})
    if preset is None:
        raise NotFoundError("CriteriaPreset", str(preset_id))
    return _preset_json(preset)


@router.delete("/presets/{preset_id}")
async def remove_preset(preset_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """删除预设；内置预设 → 409。"""
    try:
        deleted = await delete_preset(db, preset_id)
    except BuiltinPresetError as e:
        return JSONResponse(status_code=409, content={"error": str(e)})
    if not deleted:
        raise NotFoundError("CriteriaPreset", str(preset_id))
    return {"ok": True}
