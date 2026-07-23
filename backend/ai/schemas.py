"""AI Center Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NameDescription(BaseModel):
    name: str
    description: str | None = None


class PromptTemplateCreate(NameDescription):
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    output_schema: dict | None = None


class PromptTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    user_prompt_template: str | None = None
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None


class PromptTemplateResponse(PromptTemplateCreate):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class AIWorkflowCreate(NameDescription):
    workflow_type: str
    config: dict | None = None
    steps: dict | None = None


class AIWorkflowResponse(AIWorkflowCreate):
    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class GenerateRequest(BaseModel):
    prompt_name: str = Field(..., description="Name of prompt template to use")
    variables: dict = Field(default_factory=dict, description="Template variables")
    model: str | None = None
    temperature: float | None = None


class GenerateResponse(BaseModel):
    content: str
    model: str
    usage: dict | None = None
    processing_time_ms: float | None = None


class SummarizeRequest(BaseModel):
    text: str = Field(..., min_length=10)
    max_length: int = Field(default=500, le=4000)
    format: str = Field(default="paragraph", pattern="^(paragraph|bullet|json)$")


class ExtractRequest(BaseModel):
    text: str = Field(..., min_length=10)
    schema_: dict = Field(alias="schema")
