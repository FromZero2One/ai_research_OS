"""add research_evidences.inherited_from_session_id

Revision ID: a9c4d7e2f1b8
Revises: f3a8c2e1b7d9
Create Date: 2026-10-16

证据继承：标记证据来自同公司历史已完成会话（非空即继承证据）。"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "a9c4d7e2f1b8"
down_revision: str | None = "f3a8c2e1b7d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "research_evidences",
        sa.Column(
            "inherited_from_session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("research.research_sessions.id", ondelete="SET NULL"),
            nullable=True,
            comment="继承自历史已完成会话的证据（非空即继承证据）",
        ),
        schema="research",
    )


def downgrade() -> None:
    op.drop_column(
        "research_evidences", "inherited_from_session_id", schema="research"
    )
