"""AI Center API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ai.schemas import (
    AIWorkflowCreate,
    AIWorkflowResponse,
    ExtractRequest,
    GenerateRequest,
    GenerateResponse,
    PromptTemplateCreate,
    PromptTemplateUpdate,
    PromptTemplateResponse,
    SummarizeRequest,
)
from ai.service import AIService
from core.database import get_db

router = APIRouter(prefix="/ai", tags=["AI Center"])


# ── Prompt Templates ────────────────────────────────────────────────

@router.post("/templates", response_model=PromptTemplateResponse, status_code=201)
async def create_template(
    data: PromptTemplateCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = AIService(db)
    return await svc.create_template(**data.model_dump())


@router.get("/templates", response_model=list[PromptTemplateResponse])
async def list_templates(db: AsyncSession = Depends(get_db)):
    svc = AIService(db)
    return await svc.list_templates()


@router.get("/templates/{template_id}", response_model=PromptTemplateResponse)
async def get_template(template_id: str, db: AsyncSession = Depends(get_db)):
    svc = AIService(db)
    return await svc.get_template(template_id)


@router.patch("/templates/{template_id}", response_model=PromptTemplateResponse)
async def update_template(
    template_id: str,
    data: PromptTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = AIService(db)
    return await svc.update_template(template_id, **data.model_dump())


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: str, db: AsyncSession = Depends(get_db)):
    svc = AIService(db)
    await svc.delete_template(template_id)


# ── Generation ──────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate(data: GenerateRequest, db: AsyncSession = Depends(get_db)):
    svc = AIService(db)
    return await svc.generate(
        prompt_name=data.prompt_name,
        variables=data.variables,
        model=data.model,
        temperature=data.temperature,
    )


@router.post("/summarize", response_model=GenerateResponse)
async def summarize(data: SummarizeRequest, db: AsyncSession = Depends(get_db)):
    svc = AIService(db)
    return await svc.summarize(text=data.text, max_length=data.max_length, format_=data.format)


@router.post("/extract")
async def extract(data: ExtractRequest, db: AsyncSession = Depends(get_db)):
    svc = AIService(db)
    return await svc.extract(text=data.text, schema=data.schema_)


# ── Workflows ───────────────────────────────────────────────────────

@router.post("/workflows", response_model=AIWorkflowResponse, status_code=201)
async def create_workflow(
    data: AIWorkflowCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = AIService(db)
    return await svc.create_workflow(**data.model_dump())


@router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(
    workflow_id: str,
    input_data: dict,
    db: AsyncSession = Depends(get_db),
):
    svc = AIService(db)
    return await svc.execute_workflow(workflow_id, input_data)
