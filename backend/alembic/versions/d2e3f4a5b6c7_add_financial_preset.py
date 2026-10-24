"""add financial-sector builtin preset

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-24
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from screener.seeds import BUILTIN_PRESETS

revision: str = "d2e3f4a5b6c7"
down_revision: str | None = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None

_preset = sa.table(
    "criteria_presets",
    sa.column("id", postgresql.UUID(as_uuid=True)),
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("style_tag", sa.String),
    sa.column("quant_rules", postgresql.JSONB),
    sa.column("qualitative", postgresql.JSONB),
    sa.column("suggested_pool", sa.String),
    sa.column("is_builtin", sa.Boolean),
    sa.column("is_active", sa.Boolean),
    schema="screener",
)


def _financial_preset() -> dict:
    return next(p for p in BUILTIN_PRESETS if p["style_tag"] == "financial")


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT 1 FROM screener.criteria_presets "
            "WHERE is_builtin AND style_tag = 'financial' LIMIT 1"
        )
    ).first()
    if exists:
        return
    preset = _financial_preset()
    op.execute(
        _preset.insert().values(
            id=uuid.uuid4(),
            **preset,
            is_builtin=True,
            is_active=True,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM screener.criteria_presets "
            "WHERE is_builtin AND style_tag = 'financial'"
        )
    )
