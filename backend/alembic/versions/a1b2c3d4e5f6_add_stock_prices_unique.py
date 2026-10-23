"""add stock_prices (ticker, date) unique constraint

Revision ID: a1b2c3d4e5f6
Revises: f7a9c3e1b5d2
Create Date: 2026-10-23
"""
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "f7a9c3e1b5d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 幂等灌库前提：同票同日只允许一行。灌库侧先去重（backtest_data.sync_daily_to_pg）。
    op.create_unique_constraint(
        "uq_stock_prices_ticker_date",
        "stock_prices",
        ["ticker", "date"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_constraint("uq_stock_prices_ticker_date", "stock_prices", schema="market")
