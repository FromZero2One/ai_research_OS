"""add valuation metrics (pe/pb/ps) and update builtin presets

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-10-24
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from screener.seeds import BUILTIN_METRICS, BUILTIN_PRESETS

revision: str = "b7c8d9e0f1a2"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None

_VALUATION_KEYS = {"pe", "pb", "ps"}
_OLD_DESCRIPTIONS = {
    "value": "格雷厄姆式：低负债、流动比率充裕、现金流为正的便宜大市值股",
    "garp": "芒格式：质量与估值兼顾，要求盈利持续性、护城河与股东回报",
    "cycle": "逆向：周期底部的大市值低负债龙头，赌困境反转",
}

_metric = sa.table(
    "metric_defs",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("key", sa.String),
    sa.column("name_cn", sa.String),
    sa.column("category", sa.String),
    sa.column("data_source", sa.String),
    sa.column("description", sa.Text),
    schema="screener",
)
_preset = sa.table(
    "criteria_presets",
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("style_tag", sa.String),
    sa.column("quant_rules", postgresql.JSONB),
    schema="screener",
)


def upgrade() -> None:
    rows = [
        {**metric, "id": uuid.uuid4()}
        for metric in BUILTIN_METRICS
        if metric["key"] in _VALUATION_KEYS
    ]
    if rows:
        op.execute(
            postgresql.insert(_metric)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["key"])
        )

    # 内置预设只读，直接对齐 seeds.py 的最新规则（含估值条件与新描述）
    for preset in BUILTIN_PRESETS:
        op.execute(
            _preset.update()
            .where(_preset.c.style_tag == preset["style_tag"])
            .values(
                name=preset["name"],
                description=preset["description"],
                quant_rules=preset["quant_rules"],
            )
        )


def downgrade() -> None:
    for preset in BUILTIN_PRESETS:
        old_rules = [
            rule for rule in preset["quant_rules"] if rule["metric"] not in _VALUATION_KEYS
        ]
        values: dict = {"quant_rules": old_rules}
        if preset["style_tag"] in _OLD_DESCRIPTIONS:
            values["description"] = _OLD_DESCRIPTIONS[preset["style_tag"]]
        op.execute(
            _preset.update()
            .where(_preset.c.style_tag == preset["style_tag"])
            .values(**values)
        )
    op.execute(_metric.delete().where(_metric.c.key.in_(_VALUATION_KEYS)))
