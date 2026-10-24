"""Screener 预设库（v1.5）模型单测 — metric_defs / criteria_presets 表结构与内置种子。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import CriteriaPreset, MetricDef, ScreenerRun


async def test_metric_def_insert_and_query(test_session: AsyncSession):
    """metric_defs 表可插入查询，key 唯一。"""
    m = MetricDef(
        key="test_metric_x",
        name_cn="测试指标",
        category="profitability",
        data_source="yjbb",
        description="单测自建指标",
    )
    test_session.add(m)
    await test_session.flush()

    loaded = (
        await test_session.execute(select(MetricDef).where(MetricDef.key == "test_metric_x"))
    ).scalar_one()
    assert loaded.name_cn == "测试指标"
    assert loaded.category == "profitability"
    assert loaded.created_at is not None


async def test_criteria_preset_defaults(test_session: AsyncSession):
    """CriteriaPreset.quant_rules 默认 []，qualitative 默认 []，is_builtin/is_active 默认 FALSE/TRUE。"""
    p = CriteriaPreset(name="我的预设")
    test_session.add(p)
    await test_session.flush()

    loaded = (
        await test_session.execute(select(CriteriaPreset).where(CriteriaPreset.id == p.id))
    ).scalar_one()
    assert loaded.quant_rules == []
    assert loaded.qualitative == []
    assert loaded.is_builtin is False
    assert loaded.is_active is True
    assert loaded.suggested_pool == "all"


async def test_builtin_preset_seeds_exist(test_session: AsyncSession):
    """迁移种子：内置六套预设（五套通用 + 金融行业专属）。"""
    rows = (
        await test_session.execute(select(CriteriaPreset).where(CriteriaPreset.is_builtin.is_(True)))
    ).scalars().all()
    tags = {r.style_tag for r in rows}
    assert tags == {"core", "growth", "value", "garp", "cycle", "financial"}
    for r in rows:
        assert len(r.quant_rules) >= 2, f"{r.style_tag} quant_rules 为空"


async def test_financial_preset_uses_financial_metrics(test_session: AsyncSession):
    row = (
        await test_session.execute(
            select(CriteriaPreset).where(
                CriteriaPreset.is_builtin.is_(True),
                CriteriaPreset.style_tag == "financial",
            )
        )
    ).scalar_one()
    metrics = {rule["metric"] for rule in row.quant_rules}
    assert {"pb", "pe", "roe", "market_cap"} <= metrics
    assert "current_ratio" not in metrics


async def test_metric_def_seeds_exist(test_session: AsyncSession):
    """迁移种子：metric_defs 含核心指标，data_source 与采集层一致。"""
    rows = (await test_session.execute(select(MetricDef))).scalars().all()
    by_key = {r.key: r for r in rows}

    expected_sources = {
        "roe": "yjbb",
        "net_margin": "yjbb",
        "gross_margin": "yjbb",
        "revenue_growth": "yjbb",
        "net_income_growth": "yjbb",
        "debt_to_equity": "balance_sheet",
        "current_ratio": "main_finance",
        "quick_ratio": "main_finance",
        "asset_turnover": "main_finance",
        "operating_cash_flow": "cash_flow",
        "revenue": "yjbb",
        "net_income": "yjbb",
        "market_cap": "snapshot",
        "turnover": "snapshot",
        "pe": "derived",
        "pb": "derived",
        "ps": "derived",
        "cfo_to_ni": "derived",
        "cfo_to_revenue": "derived",
        "accrual_ratio": "derived",
        "roic": "main_finance",
        "interest_coverage": "main_finance",
        "cash_ratio": "main_finance",
        "fcff": "main_finance",
        "cfo_to_operating_profit": "main_finance",
        "tax_rate": "main_finance",
        "interest_debt_ratio": "main_finance",
        "peg": "derived",
        "fcf_yield": "derived",
    }
    for key, source in expected_sources.items():
        assert key in by_key, f"缺少指标种子: {key}"
        assert by_key[key].data_source == source, f"{key} data_source 应为 {source}"
    # 原 16 + 2 成长 + 3 估值 + 3 盈利质量 + 9 因子深度
    assert len(rows) >= 33


async def test_value_preset_has_valuation_rules(test_session: AsyncSession):
    """深度价值预设必须包含估值条件，否则名不副实。"""
    row = (
        await test_session.execute(
            select(CriteriaPreset).where(
                CriteriaPreset.is_builtin.is_(True),
                CriteriaPreset.style_tag == "value",
            )
        )
    ).scalar_one()
    metrics = {rule["metric"] for rule in row.quant_rules}
    assert {"pe", "pb"} <= metrics


async def test_run_v1_mode_columns_nullable(test_session: AsyncSession):
    """v1 兼容：不写 mode/preset_ids/combine_mode/pool_override 时全部为 NULL。"""
    run = ScreenerRun(criteria_hash="abc", criteria_text="自由文本标准")
    test_session.add(run)
    await test_session.flush()

    loaded = (
        await test_session.execute(select(ScreenerRun).where(ScreenerRun.id == run.id))
    ).scalar_one()
    assert loaded.mode is None
    assert loaded.preset_ids is None
    assert loaded.combine_mode is None
    assert loaded.pool_override is None
