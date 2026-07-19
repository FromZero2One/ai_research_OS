"""Research Center ORM models — the core research workflow."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.base import Base, TimestampMixin, UUIDMixin


class ResearchSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "research_sessions"
    __table_args__ = {"schema": "research"}

    title: Mapped[str] = mapped_column(String(512), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Initial context / background for this research."""

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="draft", index=True
    )
    """draft → researching → reviewing → completed → archived"""

    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Final investment thesis / conclusion."""

    decision: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    """investment decision: buy, sell, hold, watch, pass"""

    confidence: Mapped[float | None] = mapped_column(nullable=True)
    """0.0 - 1.0 confidence score."""

    tags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    evidences: Mapped[list["ResearchEvidence"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    reports: Mapped[list["ResearchReport"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ResearchEvidence(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "research_evidences"
    __table_args__ = {"schema": "research"}

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research.research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """document, market_data, web, analyst_note, ai_generated"""

    source_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    """ID of the source document or record."""

    source_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    relevance_score: Mapped[float | None] = mapped_column(nullable=True)
    evidence_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="supporting"
    )
    """supporting, opposing, neutral"""

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session: Mapped[ResearchSession] = relationship(back_populates="evidences")


class ResearchReport(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "research_reports"
    __table_args__ = {"schema": "research"}

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research.research_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(
        String(32), nullable=False, default="markdown"
    )
    """markdown, html, pdf"""

    version: Mapped[int] = mapped_column(nullable=False, default=1)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session: Mapped[ResearchSession] = relationship(back_populates="reports")
