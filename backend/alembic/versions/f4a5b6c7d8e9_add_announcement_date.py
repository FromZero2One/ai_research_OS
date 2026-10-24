"""add announcement_date to financial_metrics (point-in-time)

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "f4a5b6c7d8e9"
down_revision: str | None = "e3f4a5b6c7d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "financial_metrics",
        sa.Column("announcement_date", sa.Date(), nullable=True),
        schema="market",
    )
    op.create_index(
        "ix_market_financial_metrics_announcement_date",
        "financial_metrics",
        ["announcement_date"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_financial_metrics_announcement_date",
        table_name="financial_metrics",
        schema="market",
    )
    op.drop_column("financial_metrics", "announcement_date", schema="market")
