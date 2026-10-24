"""add screener portfolios and include cancelling in active-run guard

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d8e9f0a1b2c3"
down_revision: str | None = "c7d8e9f0a1b2"
branch_labels = None
depends_on = None

_ACTIVE = "status IN ('pending', 'screening', 'judging', 'cancelling')"


def upgrade() -> None:
    op.drop_index(
        "uq_screener_runs_active", table_name="screener_runs", schema="screener"
    )
    op.create_index(
        "uq_screener_runs_active",
        "screener_runs",
        ["status"],
        unique=True,
        schema="screener",
        postgresql_where=sa.text(_ACTIVE),
    )

    op.create_table(
        "portfolios",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("screener.screener_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column("params", postgresql.JSONB(), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=False),
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
        schema="screener",
    )
    op.create_index(
        "ix_screener_portfolios_run_id",
        "portfolios",
        ["run_id"],
        schema="screener",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_screener_portfolios_run_id", table_name="portfolios", schema="screener"
    )
    op.drop_table("portfolios", schema="screener")

    op.drop_index(
        "uq_screener_runs_active", table_name="screener_runs", schema="screener"
    )
    op.create_index(
        "uq_screener_runs_active",
        "screener_runs",
        ["status"],
        unique=True,
        schema="screener",
        postgresql_where=sa.text("status IN ('pending', 'screening', 'judging')"),
    )
