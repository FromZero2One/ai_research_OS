"""Company Center API routes — includes thesis + workspace endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from company.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
)
from core.container import Container
from core.database import get_container
from core.event_service import EventLogger
from core.exceptions import NotFoundError

router = APIRouter(prefix="/companies", tags=["Company Center"])


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    data: CompanyCreate,
    container: Container = Depends(get_container),
) -> CompanyResponse:
    svc = container.company_service
    company = await svc.create(**data.model_dump())
    return CompanyResponse.model_validate(company)


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    query: str | None = Query(None, description="Search by name or ticker"),
    sector: str | None = None,
    industry: str | None = None,
    tag: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    container: Container = Depends(get_container),
) -> CompanyListResponse:
    svc = container.company_service
    companies, total = await svc.search(
        query=query,
        sector=sector,
        industry=industry,
        tag=tag,
        skip=skip,
        limit=limit,
    )
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    container: Container = Depends(get_container),
) -> CompanyResponse:
    svc = container.company_service
    company = await svc.get(company_id)
    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    container: Container = Depends(get_container),
) -> CompanyResponse:
    svc = container.company_service
    company = await svc.update(company_id, data.model_dump(exclude_unset=True))
    return CompanyResponse.model_validate(company)


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: UUID,
    container: Container = Depends(get_container),
) -> None:
    svc = container.company_service
    await svc.delete(company_id)


# ── Thesis Panel ──────────────────────────────────────────────────────


class ThesisResponse(BaseModel):
    ticker: str
    company_name: str
    thesis: str | None = None
    decision: str | None = None
    confidence: float | None = None
    source_session_id: str | None = None
    updated_at: str | None = None
    structured_thesis: dict | None = None
    """bull_case, bear_case, key_drivers, risks from LLM analysis."""


class ThesisUpdate(BaseModel):
    thesis: str = Field(..., min_length=10)
    decision: str | None = Field(None, pattern="^(buy|sell|hold|watch|pass)$")
    confidence: float | None = Field(None, ge=0.0, le=1.0)


@router.get("/by-ticker/{ticker}/thesis", response_model=ThesisResponse)
async def get_thesis(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Get current thesis for a company (latest completed research or manual update)."""
    svc = container.company_service
    company = await svc.get_by_ticker(ticker)
    if not company:
        raise NotFoundError("Company", ticker.upper())
    result = await svc.get_thesis(ticker)
    if result:
        return ThesisResponse(**result)
    return ThesisResponse(ticker=ticker.upper(), company_name=company.name)


@router.post("/by-ticker/{ticker}/thesis", response_model=ThesisResponse)
async def update_thesis(
    ticker: str,
    data: ThesisUpdate,
    container: Container = Depends(get_container),
):
    """Manually set/update thesis for a company."""
    svc = container.company_service
    company = await svc.get_by_ticker(ticker)
    if not company:
        raise NotFoundError("Company", ticker.upper())

    logger = EventLogger(container.session)
    await logger.record(
        source="company",
        event_type="thesis.updated",
        entity_type="company",
        entity_id=ticker.upper(),
        payload=data.model_dump(),
    )
    await container.session.commit()

    return ThesisResponse(
        ticker=ticker.upper(),
        company_name=company.name,
        thesis=data.thesis,
        decision=data.decision,
        confidence=data.confidence,
        updated_at="now",
    )


@router.get("/by-ticker/{ticker}/workspace")
async def get_company_workspace(
    ticker: str,
    container: Container = Depends(get_container),
):
    """Aggregated company workspace data — thesis, timeline snippets, evidence."""
    svc = container.company_service
    result = await svc.get_workspace(ticker)
    if not result:
        raise NotFoundError("Company", ticker.upper())
    return result
