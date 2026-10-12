# ruff: noqa: E501
"""evidence classification + structured facts columns

Revision ID: a7c1e5f8b2d3
Revises: f2a8b3c9d4e7
Create Date: 2026-10-12 16:00:00.000000

新增（全部可空，历史数据无需回填）：
- research.research_evidences: classification_source / classification_confidence
- research.research_evidences: structured_facts (JSONB)
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7c1e5f8b2d3"
down_revision: str | None = "f2a8b3c9d4e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_evidences",
        sa.Column("classification_source", sa.String(16), nullable=True),
        schema="research",
    )
    op.add_column(
        "research_evidences",
        sa.Column("classification_confidence", sa.Float(), nullable=True),
        schema="research",
    )
    op.add_column(
        "research_evidences",
        sa.Column("structured_facts", JSONB(), nullable=True),
        schema="research",
    )


def downgrade() -> None:
    op.drop_column("research_evidences", "structured_facts", schema="research")
    op.drop_column("research_evidences", "classification_confidence", schema="research")
    op.drop_column("research_evidences", "classification_source", schema="research")
