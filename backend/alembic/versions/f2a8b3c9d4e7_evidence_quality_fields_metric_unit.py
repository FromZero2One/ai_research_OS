# ruff: noqa: E501
"""evidence quality fields + metric_unit

Revision ID: f2a8b3c9d4e7
Revises: abc123def456
Create Date: 2026-10-12 11:30:00.000000

新增：
- research.research_evidences: reliability / data_freshness / citation_quality
- market.financial_metrics: metric_unit
全部为可空列，历史数据无需回填，模型层保持兼容读取。
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a8b3c9d4e7"
down_revision: str | None = "abc123def456"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── 证据质量评分 ─────────────────────────────────────────────
    op.add_column(
        "research_evidences",
        sa.Column("reliability", sa.Float(), nullable=True),
        schema="research",
    )
    op.add_column(
        "research_evidences",
        sa.Column("data_freshness", sa.Integer(), nullable=True),
        schema="research",
    )
    op.add_column(
        "research_evidences",
        sa.Column("citation_quality", sa.String(32), nullable=True),
        schema="research",
    )

    # ── 财务指标单位 ─────────────────────────────────────────────
    op.add_column(
        "financial_metrics",
        sa.Column("metric_unit", sa.String(32), nullable=True),
        schema="market",
    )


def downgrade() -> None:
    op.drop_column("financial_metrics", "metric_unit", schema="market")
    op.drop_column("research_evidences", "citation_quality", schema="research")
    op.drop_column("research_evidences", "data_freshness", schema="research")
    op.drop_column("research_evidences", "reliability", schema="research")
