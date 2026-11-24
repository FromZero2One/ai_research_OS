"""Screener 预设 API — 只读查询（预设列表与指标定义库）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from screener.models import CriteriaPreset
from screener.presets import list_metrics, list_presets

router = APIRouter(tags=["Screener"])


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
