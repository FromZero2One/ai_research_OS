"""Screener 标准 API — 标准文档读写与规则翻译缓存查看。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from screener.criteria import read_criteria, write_criteria
from screener.models import ScreenerRule

router = APIRouter(tags=["Screener"])


class CriteriaUpdate(BaseModel):
    criteria: str


@router.get("/criteria")
async def get_criteria():
    """读取标准文档。"""
    return {"criteria": read_criteria()}


@router.put("/criteria")
async def update_criteria(data: CriteriaUpdate):
    """保存标准文档（文档 hash 变化会使规则翻译缓存自然失效）。"""
    write_criteria(data.criteria)
    return {"ok": True}


@router.get("/rules")
async def get_rules(db: AsyncSession = Depends(get_db)):
    """最近一次结构化规则翻译缓存（便于人工核对 LLM 理解是否正确）。"""
    rule = (
        await db.execute(select(ScreenerRule).order_by(ScreenerRule.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    if rule is None:
        return {"rules": None}
    return {"rules": rule.rules, "criteria_hash": rule.doc_hash}
