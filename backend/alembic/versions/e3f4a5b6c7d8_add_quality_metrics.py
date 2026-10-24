"""add TTM cash-flow quality metrics and update builtin presets

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-10-24
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from screener.seeds import BUILTIN_METRICS, BUILTIN_PRESETS

revision: str = "e3f4a5b6c7d8"
down_revision: str | None = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None

_QUALITY_KEYS = {"cfo_to_ni", "cfo_to_revenue", "accrual_ratio"}

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
    sa.column("style_tag", sa.String),
    sa.column("quant_rules", postgresql.JSONB),
    schema="screener",
)


def upgrade() -> None:
    rows = [
        {**metric, "id": uuid.uuid4()}
        for metric in BUILTIN_METRICS
        if metric["key"] in _QUALITY_KEYS
    ]
    if rows:
        op.execute(
            postgresql.insert(_metric)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["key"])
        )

    for preset in BUILTIN_PRESETS:
        op.execute(
            _preset.update()
            .where(_preset.c.style_tag == preset["style_tag"])
            .values(quant_rules=preset["quant_rules"])
        )


def downgrade() -> None:
    for preset in BUILTIN_PRESETS:
        old_rules = [
            rule for rule in preset["quant_rules"] if rule["metric"] not in _QUALITY_KEYS
        ]
        op.execute(
            _preset.update()
            .where(_preset.c.style_tag == preset["style_tag"])
            .values(quant_rules=old_rules)
        )
    op.execute(_metric.delete().where(_metric.c.key.in_(_QUALITY_KEYS)))
