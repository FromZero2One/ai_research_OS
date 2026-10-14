# ruff: noqa: E501
"""drop morning_briefs + macro_indicators (analyst slimming)

Revision ID: e8a2c4f6b9d1
Revises: d5e7a9c1b3f4
Create Date: 2026-10-14 12:00:00.000000

分析师瘦身（2026-10-14）：
- core.morning_briefs：旧晨报（新闻聚合噪声流）删除，为"差异日报"改造让路
- market.macro_indicators：有表无链路无 UI 的死数据，删除
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8a2c4f6b9d1"
down_revision: str | None = "d5e7a9c1b3f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("morning_briefs", schema="core")
    op.drop_table("macro_indicators", schema="market")


def downgrade() -> None:
    raise NotImplementedError(
        "downgrade for slimming drop not supported; restore via git history"
    )
