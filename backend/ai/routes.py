"""AI Center API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ai.schemas import (
    ExtractRequest,
    GenerateRequest,
    GenerateResponse,
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
    SummarizeRequest,
)
from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/ai", tags=["AI Center"])


# ── Token Usage ─────────────────────────────────────────────────────


@router.get("/usage")
async def get_llm_usage():
    """LLM token 用量汇总（进程级统计，重启清零）。"""
    from core.llm_usage import get_usage_summary

    return get_usage_summary()


# ── Prompt Templates ────────────────────────────────────────────────


@router.post("/templates", response_model=PromptTemplateResponse, status_code=201)
async def create_template(
    data: PromptTemplateCreate,
    container: Container = Depends(get_container),
):
    svc = container.ai_service
    return await svc.create_template(**data.model_dump())


@router.get("/templates", response_model=list[PromptTemplateResponse])
async def list_templates(container: Container = Depends(get_container)):
    svc = container.ai_service
    return await svc.list_templates()


@router.get("/templates/{template_id}", response_model=PromptTemplateResponse)
async def get_template(template_id: str, container: Container = Depends(get_container)):
    svc = container.ai_service
    return await svc.get_template(template_id)


@router.patch("/templates/{template_id}", response_model=PromptTemplateResponse)
async def update_template(
    template_id: str,
    data: PromptTemplateUpdate,
    container: Container = Depends(get_container),
):
    svc = container.ai_service
    return await svc.update_template(template_id, **data.model_dump())


@router.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: str, container: Container = Depends(get_container)):
    svc = container.ai_service
    await svc.delete_template(template_id)


# ── Generation ──────────────────────────────────────────────────────


@router.post("/generate", response_model=GenerateResponse)
async def generate(data: GenerateRequest, container: Container = Depends(get_container)):
    svc = container.ai_service
    return await svc.generate(
        prompt_name=data.prompt_name,
        variables=data.variables,
        model=data.model,
        temperature=data.temperature,
    )


@router.post("/summarize", response_model=GenerateResponse)
async def summarize(data: SummarizeRequest, container: Container = Depends(get_container)):
    svc = container.ai_service
    return await svc.summarize(text=data.text, max_length=data.max_length, format_=data.format)


@router.post("/extract")
async def extract(data: ExtractRequest, container: Container = Depends(get_container)):
    svc = container.ai_service
    return await svc.extract(text=data.text, schema=data.schema_)
