"""add screener tables

Revision ID: b5d2f8a3c6e1
Revises: a9c4d7e2f1b8
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b5d2f8a3c6e1"
down_revision: str | None = "a9c4d7e2f1b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS screener")
    op.create_table(
        "screener_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("status", sa.String(32), nullable=False, index=True),
        sa.Column("criteria_hash", sa.String(64), nullable=False),
        sa.Column("criteria_text", sa.Text(), nullable=False),
        sa.Column("rules", postgresql.JSONB(), nullable=True),
        sa.Column("candidate_count", sa.Integer(), nullable=True),
        sa.Column("result_count", sa.Integer(), nullable=True),
        sa.Column("report_path", sa.String(512), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(64), nullable=True),
        sa.Column("finished_at", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema="screener",
    )
    # 并发触发防线：同一时刻至多一个进行中的 run（须在建表之后创建）
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_screener_runs_active "
        "ON screener.screener_runs (status) "
        "WHERE status IN ('pending', 'screening', 'judging')"
    )
    op.create_table(
        "screener_judgements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("screener.screener_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("ticker", sa.String(16), nullable=False, index=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("recommend", sa.Boolean(), nullable=True),
        sa.Column("reasons", postgresql.JSONB(), nullable=True),
        sa.Column("criteria_hits", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema="screener",
    )
    op.create_table(
        "screener_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("doc_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("rules", postgresql.JSONB(), nullable=False),
        sa.Column("criteria_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema="screener",
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS screener.uq_screener_runs_active")
    op.drop_table("screener_rules", schema="screener")
    op.drop_table("screener_judgements", schema="screener")
    op.drop_table("screener_runs", schema="screener")
