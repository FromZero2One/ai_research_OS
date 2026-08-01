# ruff: noqa: E501
"""merge watchlist into companies

Revision ID: abc123def456
Revises: 9f4a2b6c8d01
Create Date: 2026-08-01 16:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "abc123def456"
down_revision: str | None = "9f4a2b6c8d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The watchlist concept merges into Company: "watched" == is_active, and the
    # per-item fields (priority/target_price/reason) move onto the company row.
    op.add_column(
        "companies",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        schema="company",
    )
    op.add_column(
        "companies",
        sa.Column("target_price", sa.Numeric(20, 4), nullable=True),
        schema="company",
    )
    op.add_column(
        "companies",
        sa.Column("reason", sa.Text(), nullable=True),
        schema="company",
    )

    op.drop_table("watchlist_items", schema="portfolio")
    op.drop_table("watchlists", schema="portfolio")


def downgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema="portfolio",
    )
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "watchlist_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("portfolio.watchlists.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("target_price", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
        schema="portfolio",
    )
    op.drop_column("companies", "reason", schema="company")
    op.drop_column("companies", "target_price", schema="company")
    op.drop_column("companies", "priority", schema="company")
