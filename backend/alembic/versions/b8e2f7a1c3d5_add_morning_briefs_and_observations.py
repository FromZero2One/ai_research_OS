# ruff: noqa: E501
"""add core.morning_briefs and core.observations

模型早已存在（core/morning_brief.py、core/observation.py）但从未有过对应迁移，
导致 /dashboard 查询 morning_briefs 时报 UndefinedTableError。此迁移补齐两表。

Revision ID: b8e2f7a1c3d5
Revises: a7c1e5f8b2d3
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8e2f7a1c3d5"
down_revision: str | None = "a7c1e5f8b2d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "morning_briefs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=True),
        sa.Column("stocks_covered", sa.Integer(), nullable=True),
        sa.Column("focus_stocks", sa.Integer(), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="core",
    )

    op.create_table(
        "observations",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("company_name", sa.String(length=256), nullable=False),
        sa.Column("reasons", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=True),
        sa.Column("days_since_research", sa.Integer(), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        schema="core",
    )
    op.create_index(op.f("ix_core_observations_ticker"), "observations", ["ticker"], unique=False, schema="core")


def downgrade() -> None:
    op.drop_index(op.f("ix_core_observations_ticker"), table_name="observations", schema="core")
    op.drop_table("observations", schema="core")
    op.drop_table("morning_briefs", schema="core")
