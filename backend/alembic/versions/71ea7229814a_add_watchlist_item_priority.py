"""add watchlist_item.priority column

Revision ID: 71ea7229814a
Revises: d199a3e17af8
Create Date: 2026-07-21 20:41:20.436476
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "71ea7229814a"
down_revision: Union[str, None] = "d199a3e17af8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "watchlist_items",
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("3")),
        schema="portfolio",
    )


def downgrade() -> None:
    op.drop_column("watchlist_items", "priority", schema="portfolio")
