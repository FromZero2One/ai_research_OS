"""预设 CRUD 服务单测 — 校验、内置保护、指标库列表。"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener import presets as preset_service
from screener.models import CriteriaPreset, MetricDef

_VALID_RULE = {"metric": "roe", "op": ">", "value": 10, "missing_data_policy": "exclude"}


def _preset_data(**overrides) -> dict:
    data = {
        "name": "我的低负债",
        "description": "自建测试预设",
        "style_tag": "custom",
        "quant_rules": [_VALID_RULE],
        "qualitative": ["现金流稳定"],
        "suggested_pool": "main",
    }
    data.update(overrides)
    return data


async def _get_builtin(test_session: AsyncSession, style_tag: str) -> CriteriaPreset:
    return (
        await test_session.execute(
            select(CriteriaPreset).where(
                CriteriaPreset.is_builtin.is_(True), CriteriaPreset.style_tag == style_tag
            )
        )
    ).scalar_one()


async def test_create_preset_ok(test_session: AsyncSession):
    p = await preset_service.create_preset(test_session, _preset_data())
    await test_session.flush()
    assert p.id is not None
    assert p.is_builtin is False
    assert p.quant_rules == [_VALID_RULE]


async def test_create_preset_empty_rules_rejected(test_session: AsyncSession):
    with pytest.raises(ValueError, match="quant_rules"):
        await preset_service.create_preset(test_session, _preset_data(quant_rules=[]))


async def test_create_preset_bad_op_rejected(test_session: AsyncSession):
    bad = {**_VALID_RULE, "op": "~"}
    with pytest.raises(ValueError, match="op"):
        await preset_service.create_preset(
            test_session, _preset_data(quant_rules=[bad])
        )


async def test_create_preset_unknown_metric_rejected(test_session: AsyncSession):
    bad = {**_VALID_RULE, "metric": "no_such_metric"}
    with pytest.raises(ValueError, match="metric"):
        await preset_service.create_preset(
            test_session, _preset_data(quant_rules=[bad])
        )


async def test_update_builtin_raises(test_session: AsyncSession):
    builtin = await _get_builtin(test_session, "core")
    with pytest.raises(preset_service.BuiltinPresetError):
        await preset_service.update_preset(test_session, builtin.id, {"name": "改名"})


async def test_update_user_preset_ok(test_session: AsyncSession):
    p = await preset_service.create_preset(test_session, _preset_data())
    await test_session.flush()
    updated = await preset_service.update_preset(
        test_session, p.id, {"name": "新名字", "description": "新描述"}
    )
    await test_session.flush()
    assert updated is not None
    assert updated.name == "新名字"
    # quant_rules 未在 payload 中则保持不变
    assert updated.quant_rules == [_VALID_RULE]


async def test_delete_builtin_raises(test_session: AsyncSession):
    builtin = await _get_builtin(test_session, "value")
    with pytest.raises(preset_service.BuiltinPresetError):
        await preset_service.delete_preset(test_session, builtin.id)


async def test_delete_user_preset_ok(test_session: AsyncSession):
    p = await preset_service.create_preset(test_session, _preset_data())
    await test_session.flush()
    assert await preset_service.delete_preset(test_session, p.id) is True
    await test_session.flush()
    left = (await test_session.execute(select(CriteriaPreset))).scalars().all()
    assert p.id not in {row.id for row in left}


async def test_list_presets_excludes_inactive(test_session: AsyncSession):
    await preset_service.create_preset(test_session, _preset_data(name="A"))
    p2 = await preset_service.create_preset(test_session, _preset_data(name="B"))
    p2.is_active = False
    await test_session.flush()

    names = {p.name for p in await preset_service.list_presets(test_session)}
    assert names >= {"A", "核心资产", "高成长"}  # 自建 + 内置
    assert "B" not in names
    all_names = {p.name for p in await preset_service.list_presets(test_session, include_inactive=True)}
    assert "B" in all_names


async def test_list_metrics_sorted(test_session: AsyncSession):
    metrics = await preset_service.list_metrics(test_session)
    pairs = [(m.category, m.key) for m in metrics]
    assert pairs == sorted(pairs)
    assert len(metrics) >= 12
