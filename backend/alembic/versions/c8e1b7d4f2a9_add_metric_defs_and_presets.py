"""add metric_defs and criteria_presets

Revision ID: c8e1b7d4f2a9
Revises: b5d2f8a3c6e1
Create Date: 2026-10-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from screener.seeds import insert_builtin_seeds

revision: str = "c8e1b7d4f2a9"
down_revision: str | None = "b5d2f8a3c6e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "metric_defs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("name_cn", sa.String(128), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("data_source", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema="screener",
    )
    op.create_table(
        "criteria_presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("style_tag", sa.String(32), nullable=True),
        sa.Column("quant_rules", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("qualitative", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("suggested_pool", sa.String(16), nullable=False, server_default="all"),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema="screener",
    )
    # v1.5 预设模式列（NULL = v1 自由文本运行，向后兼容）
    op.add_column("screener_runs", sa.Column("mode", sa.String(16), nullable=True), schema="screener")
    op.add_column("screener_runs", sa.Column("preset_ids", postgresql.JSONB(), nullable=True), schema="screener")
    op.add_column("screener_runs", sa.Column("combine_mode", sa.String(16), nullable=True), schema="screener")
    op.add_column("screener_runs", sa.Column("pool_override", sa.String(16), nullable=True), schema="screener")
    # 内置种子（唯一事实源：screener/seeds.py）
    insert_builtin_seeds(op.get_bind())


def downgrade() -> None:
    op.drop_column("screener_runs", "pool_override", schema="screener")
    op.drop_column("screener_runs", "combine_mode", schema="screener")
    op.drop_column("screener_runs", "preset_ids", schema="screener")
    op.drop_column("screener_runs", "mode", schema="screener")
    op.drop_table("criteria_presets", schema="screener")
    op.drop_table("metric_defs", schema="screener")
