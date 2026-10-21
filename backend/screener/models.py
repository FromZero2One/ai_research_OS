"""Screener ORM models — 选股运行、深判结果、标准翻译缓存。"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, TimestampMixin, UUIDMixin


class ScreenerRun(Base, UUIDMixin, TimestampMixin):
    """一次选股运行的完整记录（状态机 pending → screening → judging → completed/failed）。"""

    __tablename__ = "screener_runs"
    __table_args__ = {"schema": "screener"}

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending", index=True)
    criteria_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    criteria_text: Mapped[str] = mapped_column(Text, nullable=False)
    rules: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    candidate_count: Mapped[int | None] = mapped_column(nullable=True)
    result_count: Mapped[int | None] = mapped_column(nullable=True)
    report_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    finished_at: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ScreenerJudgement(Base, UUIDMixin, TimestampMixin):
    """单只候选的 LLM 深判结果（recommend 可空 — 深判失败时无结论）。"""

    __tablename__ = "screener_judgements"
    __table_args__ = {"schema": "screener"}

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("screener.screener_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    recommend: Mapped[bool | None] = mapped_column(nullable=True)
    reasons: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    criteria_hits: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # ok | failed — 单只深判失败不拖垮整次运行
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ScreenerRule(Base, UUIDMixin, TimestampMixin):
    """标准文档翻译缓存 — doc_hash 未变则跳过 LLM 翻译。"""

    __tablename__ = "screener_rules"
    __table_args__ = {"schema": "screener"}

    doc_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    rules: Mapped[dict] = mapped_column(JSONB, nullable=False)
    criteria_text: Mapped[str] = mapped_column(Text, nullable=False)
