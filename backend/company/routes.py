"""Company routes — read-only list (document association picker).

公司中心 CRUD/thesis/自选已随五次简化退役；Company 表与模型保留
（screener 数据质量统计、market search/profile、document.company_id 外键
仍在读）。唯一保留的端点是列表查询，供文档中心「关联公司」下拉使用。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from company.schemas import CompanyListResponse, CompanyResponse
from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/companies", tags=["Company Center"])


@router.get("", response_model=CompanyListResponse)
async def list_companies(
    query: str | None = Query(None, description="Search by name or ticker"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    container: Container = Depends(get_container),
) -> CompanyListResponse:
    svc = container.company_service
    companies, total = await svc.search(query=query, skip=skip, limit=limit)
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in companies],
        total=total,
    )
