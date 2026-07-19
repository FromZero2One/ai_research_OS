"""AI Center ORM models — prompts, workflows, LLM configs."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, TimestampMixin, UUIDMixin


class PromptTemplate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "prompt_templates"
    __table_args__ = {"schema": "ai"}

    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_prompt_template: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    temperature: Mapped[float | None] = mapped_column(nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_schema: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AIWorkflow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "ai_workflows"
    __table_args__ = {"schema": "ai"}

    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512), nullable=True)
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """workflow_type: summarization, extraction, reasoning, research, custom"""
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    steps: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """List of step definitions for multi-step workflows (LangGraph-compatible)."""
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
