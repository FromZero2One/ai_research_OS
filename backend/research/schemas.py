"""Research Center Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ResearchPlan(BaseModel):
    """AI-generated research plan stored in session.extra_metadata."""

    research_goal: str = Field(..., description="Restated research goal")
    sub_questions: list[str] = Field(..., description="Sub-questions to answer", max_length=10)
    analysis_dimensions: list[str] = Field(..., description="Analysis dimensions (financial, industry, etc.)")
    data_requirements: list[str] = Field(default=[], description="Data to collect")
    suggested_sources: list[str] = Field(default=[], description="Types of sources to search")


class ResearchSessionCreate(BaseModel):
    title: str = Field(..., max_length=512)
    question: str = Field(..., min_length=10)
    context: str | None = None
    company_id: UUID | None = None
    tags: list[str] | None = None
    auto_plan: bool = Field(default=False, description="Auto-generate research plan on create")


class ResearchSessionUpdate(BaseModel):
    title: str | None = None
    question: str | None = None
    context: str | None = None
    thesis: str | None = None
    decision: str | None = Field(None, pattern="^(buy|sell|hold|watch|pass|)$")
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    status: str | None = Field(None, pattern="^(draft|researching|reviewing|completed|archived)$")
    tags: list[str] | None = None


class EvidenceCreate(BaseModel):
    content: str = Field(..., min_length=10)
    source_type: str
    source_id: str | None = None
    source_title: str | None = None
    relevance_score: float | None = Field(None, ge=0.0, le=1.0)
    evidence_type: str = Field(default="supporting", pattern="^(supporting|opposing|neutral)$")
    summary: str | None = None
    metadata: dict | None = None


class ResearchSessionResponse(BaseModel):
    id: UUID
    title: str
    question: str
    context: str | None
    company_id: UUID | None
    status: str
    thesis: str | None
    decision: str | None
    confidence: float | None
    tags: dict | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class ResearchSessionDetail(ResearchSessionResponse):
    evidences: list["EvidenceResponse"] = []
    reports: list["ReportResponse"] = []
    plan: ResearchPlan | None = None

    @model_validator(mode="before")
    @classmethod
    def extract_plan(cls, data: any) -> any:
        """Extract research plan from session.extra_metadata."""
        if isinstance(data, dict):
            extra = data.get("extra_metadata") or {}
        else:
            extra = getattr(data, "extra_metadata", None) or {}
        plan_data = extra.get("research_plan") if isinstance(extra, dict) else None
        if isinstance(data, dict):
            data["plan"] = plan_data
        else:
            data.plan = plan_data if plan_data else None
        return data


class EvidenceResponse(BaseModel):
    id: UUID
    session_id: UUID
    content: str
    source_type: str
    source_id: str | None
    source_title: str | None
    relevance_score: float | None
    evidence_type: str
    summary: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportResponse(BaseModel):
    id: UUID
    session_id: UUID
    title: str
    content: str
    format: str
    version: int
    is_final: bool
    created_at: datetime

    model_config = {"from_attributes": True}
