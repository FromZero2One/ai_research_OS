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

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    """draft → researching → reviewing → completed → archived"""

    thesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Final investment thesis / conclusion."""

    decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    """investment decision: buy, sell, hold, watch, pass"""

    confidence: Mapped[float | None] = mapped_column(nullable=True)
    """0.0 - 1.0 confidence score."""

    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    evidences: Mapped[list[ResearchEvidence]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        # 表间存在两个外键（session_id / inherited_from_session_id），需显式指定连接键
        foreign_keys="ResearchEvidence.session_id",
    )
    reports: Mapped[list[ResearchReport]] = relationship(
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
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False, default="supporting")
    """supporting, opposing, neutral"""

    content_nature: Mapped[str | None] = mapped_column(
        String(16),
        nullable=True,
        comment="论断性质：quantitative（数字）/ qualitative（定性），NULL=未知",
    )
    """报告双轨：数字论断引用 Market 区块，定性论断内联 [ev:id] 回跳原文"""

    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # ── 新增：证据质量评分 ────────────────────────────────────────
    reliability: Mapped[float | None] = mapped_column(
        nullable=True,
        comment="0.0-1.0 证据可靠性评分（来源可信度、数据质量综合评分）",
    )
    data_freshness: Mapped[int | None] = mapped_column(
        nullable=True,
        comment="数据新鲜度（小时数），None表示未知或不适用",
    )
    citation_quality: Mapped[str | None] = mapped_column(
        nullable=True,
        comment="引用质量等级：peer_reviewed、institutional、analyst、internal",
    )

    # ── 新增：LLM 分类与结构化事实 ────────────────────────────────
    classification_source: Mapped[str | None] = mapped_column(
        nullable=True,
        comment="evidence_type 的判定来源：llm | keyword（审计用）",
    )
    classification_confidence: Mapped[float | None] = mapped_column(
        nullable=True,
        comment="0.0-1.0 分类置信度（LLM 自评，keyword 分类为 NULL）",
    )
    structured_facts: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="从证据文本抽取的结构化财务事实 JSON（{facts: [...], not_mentioned: bool}）",
    )

    inherited_from_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research.research_sessions.id", ondelete="SET NULL"),
        nullable=True,
        comment="继承自历史已完成会话的证据（非空即继承证据）",
    )
    # ----------------------------------------------------------------

    session: Mapped[ResearchSession] = relationship(
        back_populates="evidences",
        foreign_keys=[session_id],
    )


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
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="markdown")
    """markdown, html, pdf"""

    version: Mapped[int] = mapped_column(nullable=False, default=1)
    is_final: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    session: Mapped[ResearchSession] = relationship(back_populates="reports")
