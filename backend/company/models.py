"""Company Center ORM models."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import ForeignKey, String, Text, Date
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.base import Base, TimestampMixin, UUIDMixin


class Company(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "companies"
    __table_args__ = {"schema": "company"}

    ticker: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    headquarters: Mapped[str | None] = mapped_column(String(256), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(nullable=True)
    employees: Mapped[int | None] = mapped_column(nullable=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    tags: Mapped[list[CompanyTag]] = relationship(
        back_populates="company", cascade="all, delete-orphan"
    )


class CompanyTag(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "company_tags"
    __table_args__ = {"schema": "company"}

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("company.companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    tag: Mapped[str] = mapped_column(String(64), nullable=False)

    company: Mapped[Company] = relationship(back_populates="tags")
