"""Company Center API routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from company.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
)
from company.service import CompanyService
from core.database import get_db

router = APIRouter(prefix="/companies", tags=["Company Center"])


@router.post("", response_model=CompanyResponse, status_code=201)
async def create_company(
    data: CompanyCreate,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    svc = CompanyService(db)
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
    db: AsyncSession = Depends(get_db),
) -> CompanyListResponse:
    svc = CompanyService(db)
    companies, total = await svc.search(
        query=query, sector=sector, industry=industry,
        tag=tag, skip=skip, limit=limit,
    )
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
    )


@router.get("/{company_id}", response_model=CompanyResponse)
async def get_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    svc = CompanyService(db)
    company = await svc.get(company_id)
    return CompanyResponse.model_validate(company)


@router.patch("/{company_id}", response_model=CompanyResponse)
async def update_company(
    company_id: UUID,
    data: CompanyUpdate,
    db: AsyncSession = Depends(get_db),
) -> CompanyResponse:
    svc = CompanyService(db)
    company = await svc.update(company_id, data.model_dump(exclude_unset=True))
    return CompanyResponse.model_validate(company)


@router.delete("/{company_id}", status_code=204)
async def delete_company(
    company_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    svc = CompanyService(db)
    await svc.delete(company_id)
