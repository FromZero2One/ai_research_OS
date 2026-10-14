# ruff: noqa: E501
"""chunk content_type + evidence content_nature

Revision ID: d5e7a9c1b3f4
Revises: c3d5e7a9b1f2
Create Date: 2026-10-14 10:00:00.000000

数据分工原则（接口管"数"，PDF 管"事"）落地：
- document.document_chunks: content_type（mda/risk/notes/announcement/other，
  server_default='other'，历史切片保持 other，重新索引后自动打标）
- research.research_evidences: content_nature（quantitative/qualitative，
  可空=未知；市场数据类证据入库即写 quantitative）
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5e7a9c1b3f4"
down_revision: str | None = "c3d5e7a9b1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "document_chunks",
        sa.Column(
            "content_type",
            sa.String(32),
            nullable=False,
            server_default="other",
            comment="切片内容类型：mda/risk/notes/announcement/other",
        ),
        schema="document",
    )
    op.create_index(
        "ix_document_chunks_content_type",
        "document_chunks",
        ["content_type"],
        schema="document",
    )
    op.add_column(
        "research_evidences",
        sa.Column(
            "content_nature",
            sa.String(16),
            nullable=True,
            comment="论断性质：quantitative（数字）/ qualitative（定性），NULL=未知",
        ),
        schema="research",
    )


def downgrade() -> None:
    op.drop_column("research_evidences", "content_nature", schema="research")
    op.drop_index(
        "ix_document_chunks_content_type", table_name="document_chunks", schema="document"
    )
    op.drop_column("document_chunks", "content_type", schema="document")
