"""add backtest_runs table

Revision ID: f7a9c3e1b5d2
Revises: e2b6f4a8c9d1
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "f7a9c3e1b5d2"
down_revision = "e2b6f4a8c9d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("preset_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("years", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("result", JSONB, nullable=True),
        sa.Column("report_path", sa.String(512), nullable=True),
        sa.Column("started_at", sa.String(64), nullable=True),
        sa.Column("finished_at", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="screener",
    )


def downgrade() -> None:
    op.drop_table("backtest_runs", schema="screener")
