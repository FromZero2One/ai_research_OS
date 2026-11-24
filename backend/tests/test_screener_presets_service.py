"""预设只读服务单测 — 列表查询与指标库排序。"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from screener import presets as preset_service
from screener.models import CriteriaPreset


async def test_list_presets_includes_builtins(test_session: AsyncSession):
    names = {p.name for p in await preset_service.list_presets(test_session)}
    assert {"核心资产", "高成长"} <= names


async def test_list_presets_excludes_inactive(test_session: AsyncSession):
    p2 = CriteriaPreset(
        name="隐藏预设", quant_rules=[{"metric": "roe", "op": ">", "value": 10}],
        qualitative=[], is_builtin=False, is_active=False,
    )
    test_session.add(p2)
    await test_session.flush()

    names = {p.name for p in await preset_service.list_presets(test_session)}
    assert "隐藏预设" not in names
    all_names = {p.name for p in await preset_service.list_presets(test_session, include_inactive=True)}
    assert "隐藏预设" in all_names


async def test_list_metrics_sorted(test_session: AsyncSession):
    metrics = await preset_service.list_metrics(test_session)
    pairs = [(m.category, m.key) for m in metrics]
    assert pairs == sorted(pairs)
    assert len(metrics) >= 12
