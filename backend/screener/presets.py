"""预设只读服务 — 预设/指标库查询（纯 async SQLAlchemy，无 LLM）。

预设仅由种子数据维护（screener/seeds.py），不再提供 CRUD。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import CriteriaPreset, MetricDef


async def list_presets(db: AsyncSession, include_inactive: bool = False) -> list[CriteriaPreset]:
    """预设列表（内置 + 自建），内置在前、按创建时间。"""
    stmt = select(CriteriaPreset).order_by(CriteriaPreset.is_builtin.desc(), CriteriaPreset.created_at)
    if not include_inactive:
        stmt = stmt.where(CriteriaPreset.is_active.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def get_preset(db: AsyncSession, preset_id: uuid.UUID) -> CriteriaPreset | None:
    return await db.get(CriteriaPreset, preset_id)


async def list_metrics(db: AsyncSession) -> list[MetricDef]:
    """指标库，按 category, key 排序（前端按分类分组展示）。

    Python 侧排序：PG collation 忽略下划线，与代码内断言/展示预期不一致。
    """
    rows = (await db.execute(select(MetricDef))).scalars().all()
    return sorted(rows, key=lambda m: (m.category, m.key))
