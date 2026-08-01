# ruff: noqa: E501
"""add data_freshness table

Revision ID: c97c9a0dcf69
Revises: d0eafc46e5cc
Create Date: 2026-07-29 22:38:54.600533
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c97c9a0dcf69"
down_revision: str | None = "d0eafc46e5cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Only create data_freshness table — other tables already exist
    op.create_table(
        "data_freshness",
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("record_count", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.PrimaryKeyConstraint("id"),
        schema="market",
    )
    op.create_index(
        op.f("ix_market_data_freshness_id"), "data_freshness", ["id"], unique=False, schema="market"
    )
    op.create_index(
        op.f("ix_market_data_freshness_ticker"),
        "data_freshness",
        ["ticker"],
        unique=False,
        schema="market",
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_market_data_freshness_ticker"), table_name="data_freshness", schema="market"
    )
    op.drop_index(op.f("ix_market_data_freshness_id"), table_name="data_freshness", schema="market")
    op.drop_table("data_freshness", schema="market")
