"""add screener judgement verdict

Revision ID: a5b6c7d8e9f0
Revises: f4a5b6c7d8e9
Create Date: 2026-10-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "a5b6c7d8e9f0"
down_revision: str | None = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "screener_judgements",
        sa.Column("verdict", sa.String(16), nullable=True),
        schema="screener",
    )
    op.create_index(
        "ix_screener_judgements_verdict",
        "screener_judgements",
        ["verdict"],
        schema="screener",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_screener_judgements_verdict",
        table_name="screener_judgements",
        schema="screener",
    )
    op.drop_column("screener_judgements", "verdict", schema="screener")
