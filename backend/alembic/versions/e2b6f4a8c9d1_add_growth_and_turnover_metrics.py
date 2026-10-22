"""add growth and turnover metrics; fix metric definitions

- 新增 revenue_growth / net_income_growth 指标定义
- 流动/速动/周转类指标数据源改为 main_finance（F10 主要指标）
- debt_to_equity 名称/描述与实际实现（D/E）对齐
- 内置「高成长」预设改用营收/净利同比

Revision ID: e2b6f4a8c9d1
Revises: c8e1b7d4f2a9
Create Date: 2026-10-22
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "e2b6f4a8c9d1"
down_revision: str | None = "c8e1b7d4f2a9"
branch_labels = None
depends_on = None

metric_defs = sa.table(
    "metric_defs",
    sa.column("id", sa.Uuid),
    sa.column("key", sa.String),
    sa.column("name_cn", sa.String),
    sa.column("category", sa.String),
    sa.column("data_source", sa.String),
    sa.column("description", sa.Text),
    schema="screener",
)
presets = sa.table(
    "criteria_presets",
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("quant_rules", postgresql.JSONB),
    sa.column("qualitative", postgresql.JSONB),
    sa.column("is_builtin", sa.Boolean),
    sa.column("updated_at", sa.DateTime(timezone=True)),
    schema="screener",
)

NEW_METRICS: list[dict] = [
    {
        "key": "revenue_growth",
        "name_cn": "营业收入同比(%)",
        "category": "growth",
        "data_source": "yjbb",
        "description": "营业总收入同比增长率",
    },
    {
        "key": "net_income_growth",
        "name_cn": "净利润同比(%)",
        "category": "growth",
        "data_source": "yjbb",
        "description": "归母净利润同比增长率",
    },
]

NEW_GROWTH_RULES: list[dict] = [
    {"metric": "revenue_growth", "op": ">", "value": 20, "missing_data_policy": "exclude"},
    {"metric": "net_income_growth", "op": ">", "value": 20, "missing_data_policy": "exclude"},
    {"metric": "roe", "op": ">", "value": 12, "missing_data_policy": "exclude"},
    {"metric": "net_margin", "op": ">", "value": 8, "missing_data_policy": "exclude"},
    {"metric": "market_cap", "op": ">", "value": 1e10, "missing_data_policy": "exclude"},
]
OLD_GROWTH_RULES: list[dict] = [
    {"metric": "roe", "op": ">", "value": 12, "missing_data_policy": "exclude"},
    {"metric": "net_margin", "op": ">", "value": 8, "missing_data_policy": "exclude"},
    {"metric": "market_cap", "op": ">", "value": 1e10, "missing_data_policy": "exclude"},
]
NEW_GROWTH_DESC = "费雪式：营收与净利润双高增长的中大市值成长股，配合定性赛道判断"
OLD_GROWTH_DESC = "费雪式：盈利能力达标的中大市值成长股，配合定性赛道判断"
NEW_GROWTH_QUAL = ["所处行业渗透率持续提升", "增长由主营业务驱动", "细分行业排名前二"]
OLD_GROWTH_QUAL = ["所处行业渗透率正在提升", "增长由主营业务驱动", "细分行业排名前二"]

_MAIN_FINANCE_KEYS = (
    "current_ratio",
    "quick_ratio",
    "asset_turnover",
    "inventory_turnover",
    "receivables_turnover",
)


def _insert_missing_metrics(bind: sa.Connection) -> None:
    for metric in NEW_METRICS:
        exists = bind.execute(
            sa.select(metric_defs.c.id).where(metric_defs.c.key == metric["key"])
        ).first()
        if exists is None:
            bind.execute(metric_defs.insert().values(id=uuid.uuid4(), **metric))


def _update_growth_preset(
    bind: sa.Connection,
    description: str,
    quant_rules: list[dict],
    qualitative: list[str],
) -> None:
    bind.execute(
        presets.update()
        .where(presets.c.name == "高成长", presets.c.is_builtin.is_(True))
        .values(
            description=description,
            quant_rules=quant_rules,
            qualitative=qualitative,
            updated_at=sa.func.now(),
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    _insert_missing_metrics(bind)
    bind.execute(
        metric_defs.update()
        .where(metric_defs.c.key == "debt_to_equity")
        .values(
            name_cn="负债权益比(%)",
            description="总负债 / 股东权益 × 100（D/E）",
        )
    )
    for key in _MAIN_FINANCE_KEYS:
        bind.execute(
            metric_defs.update().where(metric_defs.c.key == key).values(data_source="main_finance")
        )
    _update_growth_preset(bind, NEW_GROWTH_DESC, NEW_GROWTH_RULES, NEW_GROWTH_QUAL)


def downgrade() -> None:
    bind = op.get_bind()
    _update_growth_preset(bind, OLD_GROWTH_DESC, OLD_GROWTH_RULES, OLD_GROWTH_QUAL)
    for key in _MAIN_FINANCE_KEYS:
        bind.execute(
            metric_defs.update().where(metric_defs.c.key == key).values(data_source="balance_sheet")
        )
    bind.execute(
        metric_defs.update()
        .where(metric_defs.c.key == "debt_to_equity")
        .values(name_cn="资产负债率(%)", description="总负债 / 总资产")
    )
    bind.execute(
        metric_defs.delete().where(
            metric_defs.c.key.in_([m["key"] for m in NEW_METRICS])
        )
    )
