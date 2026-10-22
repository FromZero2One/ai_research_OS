"""预设 CRUD 服务 — 内置预设保护 + 指标库查询（纯 async SQLAlchemy，无 LLM）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import CriteriaPreset, MetricDef

_ALLOWED_OPS = frozenset({">", "<", ">=", "<="})

# 预设可更新的字段（id/is_builtin/created_at 不接受外部写入）
_UPDATABLE_FIELDS = {"name", "description", "style_tag", "quant_rules", "qualitative", "suggested_pool", "is_active"}


class BuiltinPresetError(Exception):
    """内置预设不可修改/删除。"""


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


async def _validate_metrics_exist(db: AsyncSession, quant_rules: list) -> None:
    keys = {r.get("metric") for r in quant_rules}
    rows = (await db.execute(select(MetricDef.key).where(MetricDef.key.in_(keys)))).scalars().all()
    unknown = keys - set(rows)
    if unknown:
        raise ValueError(f"quant_rules.metric 不在指标库中: {sorted(unknown)}")


async def _validate_quant_rules(db: AsyncSession, quant_rules: list) -> None:
    """quant_rules 校验：非空、metric 在指标库、op 合法、value 为数字。"""
    if not isinstance(quant_rules, list) or not quant_rules:
        raise ValueError("quant_rules 不能为空（至少一条量化规则）")
    for i, rule in enumerate(quant_rules):
        if not isinstance(rule, dict):
            raise ValueError(f"quant_rules[{i}] 必须是对象")
        op = rule.get("op")
        value = rule.get("value")
        if op not in _ALLOWED_OPS:
            raise ValueError(f"quant_rules[{i}].op 非法: {op!r}（允许 {sorted(_ALLOWED_OPS)}）")
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"quant_rules[{i}].value 必须是数字")
        if rule.get("metric") is None:
            raise ValueError(f"quant_rules[{i}].metric 缺失")
    await _validate_metrics_exist(db, quant_rules)


def _validate_qualitative(qualitative: list) -> None:
    if not isinstance(qualitative, list) or any(not isinstance(q, str) for q in qualitative):
        raise ValueError("qualitative 必须是字符串数组")


async def create_preset(db: AsyncSession, data: dict) -> CriteriaPreset:
    """新建用户预设。校验失败 raise ValueError。"""
    quant_rules = data.get("quant_rules")
    await _validate_quant_rules(db, quant_rules)
    _validate_qualitative(data.get("qualitative", []))
    preset = CriteriaPreset(
        name=data["name"],
        description=data.get("description"),
        style_tag=data.get("style_tag", "custom"),
        quant_rules=quant_rules,
        qualitative=data.get("qualitative", []),
        suggested_pool=data.get("suggested_pool", "all"),
        is_builtin=False,
        is_active=True,
    )
    db.add(preset)
    await db.flush()
    return preset


async def update_preset(db: AsyncSession, preset_id: uuid.UUID, data: dict) -> CriteriaPreset | None:
    """更新预设；内置预设 raise BuiltinPresetError。"""
    preset = await db.get(CriteriaPreset, preset_id)
    if preset is None:
        return None
    if preset.is_builtin:
        raise BuiltinPresetError("内置预设不可修改，请复制后编辑")
    if "quant_rules" in data:
        await _validate_quant_rules(db, data["quant_rules"])
    if "qualitative" in data:
        _validate_qualitative(data["qualitative"])
    if "name" in data and not str(data["name"]).strip():
        raise ValueError("预设名称不能为空")
    for field in _UPDATABLE_FIELDS:
        if field in data:
            setattr(preset, field, data[field])
    await db.flush()
    return preset


async def delete_preset(db: AsyncSession, preset_id: uuid.UUID) -> bool:
    """删除预设；内置预设 raise BuiltinPresetError。返回是否删除。"""
    preset = await db.get(CriteriaPreset, preset_id)
    if preset is None:
        return False
    if preset.is_builtin:
        raise BuiltinPresetError("内置预设不可删除")
    await db.delete(preset)
    await db.flush()
    return True
