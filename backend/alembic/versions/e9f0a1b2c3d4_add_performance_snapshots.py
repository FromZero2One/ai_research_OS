"""add screener performance snapshots

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e9f0a1b2c3d4"
down_revision: str | None = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "performance_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("screener.screener_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("stocks", postgresql.JSONB(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.UniqueConstraint("run_id", "as_of", name="uq_perf_snapshot_run_date"),
        schema="screener",
    )
    op.create_index(
        "ix_screener_perf_snapshots_run_id",
        "performance_snapshots",
        ["run_id"],
        schema="screener",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_screener_perf_snapshots_run_id",
        table_name="performance_snapshots",
        schema="screener",
    )
    op.drop_table("performance_snapshots", schema="screener")
