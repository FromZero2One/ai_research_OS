"""add market.stock_industry

Revision ID: c1d2e3f4a5b6
Revises: b7c8d9e0f1a2
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_industry",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("industry_code", sa.String(32), nullable=True),
        sa.Column("industry_name", sa.String(64), nullable=True),
        sa.Column("source", sa.String(16), nullable=False, server_default="sina"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=True,
        ),
        sa.UniqueConstraint("ticker", name="uq_stock_industry_ticker"),
        schema="market",
    )
    op.create_index(
        "ix_market_stock_industry_ticker", "stock_industry", ["ticker"], schema="market"
    )
    op.create_index(
        "ix_market_stock_industry_industry_name",
        "stock_industry",
        ["industry_name"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_stock_industry_industry_name",
        table_name="stock_industry",
        schema="market",
    )
    op.drop_index(
        "ix_market_stock_industry_ticker", table_name="stock_industry", schema="market"
    )
    op.drop_table("stock_industry", schema="market")
