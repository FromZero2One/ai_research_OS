"""add pg_trgm index on document chunks for ILIKE fallback search

Revision ID: 9f4a2b6c8d01
Revises: c97c9a0dcf69
Create Date: 2026-08-01 10:30:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f4a2b6c8d01"
down_revision: str | None = "c97c9a0dcf69"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEX_NAME = "ix_document_chunks_content_trgm"


def upgrade() -> None:
    # GIN trigram index accelerates ILIKE '%query%' on chunk content
    # (used by knowledge service's DB text-search fallback).
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {INDEX_NAME} "
        "ON document.document_chunks USING gin (content gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX_NAME}")
