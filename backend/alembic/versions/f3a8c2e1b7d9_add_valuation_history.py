"""add market.valuation_history (PE/PB percentile source)

Revision ID: f3a8c2e1b7d9
Revises: e8a2c4f6b9d1
Create Date: 2026-10-15

比率层（2026-10-15）：A 股估值历史全序列入 PG，供 PE/PB 历史分位计算。首次访问经 akshare 子进程（stock_a_indicator_lg）拉全量，之后只查 PG。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "f3a8c2e1b7d9"
down_revision: str | None = "e8a2c4f6b9d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "valuation_history",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("pe", sa.Float(), nullable=True),
        sa.Column("pe_ttm", sa.Float(), nullable=True),
        sa.Column("pb", sa.Float(), nullable=True),
        sa.Column("total_mv", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("ticker", "trade_date", name="uq_valuation_ticker_date"),
        schema="market",
    )
    op.create_index(
        "ix_market_valuation_history_ticker",
        "valuation_history",
        ["ticker"],
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_market_valuation_history_ticker",
        table_name="valuation_history",
        schema="market",
    )
    op.drop_table("valuation_history", schema="market")
