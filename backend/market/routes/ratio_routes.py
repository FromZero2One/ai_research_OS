"""Ratio endpoints — 财务比率（近 N 期）+ A股估值历史分位。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from core.container import Container
from core.database import get_container

router = APIRouter(prefix="/market/ratios", tags=["Market Center"])


@router.get("/{ticker}")
async def get_ratios(
    ticker: str,
    limit: int = Query(default=3, le=10, description="返回最近 N 期"),
    container: Container = Depends(get_container),
):
    """最近 N 期财务比率（衍生毛利率/净利率 + 透出 ROE/资产负债率/周转率等）。"""
    ratios = await container.ratio_service.read_ratios(ticker, limit=limit)
    return {"ticker": ticker.upper(), "ratios": ratios}


@router.get("/{ticker}/valuation-percentile")
async def get_valuation_percentile(
    ticker: str,
    container: Container = Depends(get_container),
):
    """PE/PE-TTM/PB 历史分位（仅 A 股；无数据时 available=false，不报错）。"""
    return await container.ratio_service.valuation_percentile(ticker)
