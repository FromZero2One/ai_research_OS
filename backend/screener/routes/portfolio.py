"""Screener 组合 API — 构建、保存、查看、再平衡、删除。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.exceptions import NotFoundError
from market.models import StockPrice
from screener.models import ScreenerJudgement, ScreenerRun
from screener.portfolio import construct_portfolio
from screener.portfolio_store import (
    delete_portfolio,
    get_portfolio,
    list_portfolios,
    portfolio_json,
    save_portfolio,
)
from screener.rebalance import compute_rebalance

router = APIRouter(tags=["Screener"])


class PortfolioParams(BaseModel):
    """POST /runs/{id}/portfolio body。"""

    capital: float = Field(default=1_000_000.0, gt=0)
    method: str = "equal"
    max_weight: float = Field(default=0.15, gt=0, le=1)
    max_industry_weight: float = Field(default=0.35, gt=0, le=1)
    max_holdings: int = Field(default=20, ge=1, le=100)
    save: bool = False
    name: str | None = Field(default=None, max_length=128)


class RebalanceParams(BaseModel):
    """POST /portfolios/{id}/rebalance body。"""

    tolerance: float = Field(default=0.01, ge=0, le=0.5)
    lot_size: int = Field(default=100, ge=1, le=1000)


@router.post("/runs/{run_id}/portfolio")
async def build_portfolio(
    run_id: uuid.UUID,
    params: PortfolioParams,
    db: AsyncSession = Depends(get_db),
):
    """推荐股 → 资金分配（单票/行业上限，约束冲突时保留现金）。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    judgements = (
        await db.execute(
            select(ScreenerJudgement).where(
                ScreenerJudgement.run_id == run.id,
                ScreenerJudgement.status == "ok",
                ScreenerJudgement.recommend.is_(True),
            )
        )
    ).scalars().all()
    candidates = []
    for j in judgements:
        snapshot = j.snapshot or {}
        candidates.append(
            {
                "ticker": j.ticker,
                "name": j.name,
                "industry": snapshot.get("industry"),
                "price": snapshot.get("price"),
                "score": snapshot.get("score"),
                "confidence": j.confidence,
            }
        )
    try:
        result = construct_portfolio(
            candidates,
            capital=params.capital,
            method=params.method,
            max_weight=params.max_weight,
            max_industry_weight=params.max_industry_weight,
            max_holdings=params.max_holdings,
        )
    except ValueError as e:
        return JSONResponse(status_code=422, content={"error": str(e)})

    payload = {"run_id": str(run.id), **result}
    if params.save:
        row = await save_portfolio(
            db,
            run.id,
            {
                "capital": params.capital,
                "method": params.method,
                "max_weight": params.max_weight,
                "max_industry_weight": params.max_industry_weight,
                "max_holdings": params.max_holdings,
            },
            result,
            name=params.name,
        )
        await db.commit()
        payload["portfolio_id"] = str(row.id)
        payload["name"] = row.name
    return payload


@router.get("/portfolios")
async def list_all_portfolios(db: AsyncSession = Depends(get_db)):
    """全部已保存组合（最新在前）。"""
    rows = await list_portfolios(db)
    return {"portfolios": [portfolio_json(p) for p in rows]}


@router.get("/runs/{run_id}/portfolios")
async def list_run_portfolios(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """某轮运行下已保存的组合方案。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    rows = await list_portfolios(db, run_id)
    return {"portfolios": [portfolio_json(p) for p in rows]}


@router.get("/portfolios/{portfolio_id}")
async def get_saved_portfolio(
    portfolio_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """已保存组合详情。"""
    row = await get_portfolio(db, portfolio_id)
    if row is None:
        raise NotFoundError("ScreenerPortfolio", str(portfolio_id))
    return portfolio_json(row)


@router.post("/portfolios/{portfolio_id}/rebalance")
async def rebalance_saved_portfolio(
    portfolio_id: uuid.UUID,
    params: RebalanceParams,
    db: AsyncSession = Depends(get_db),
):
    """按最新收盘价计算已保存组合的漂移与买卖建议。"""
    row = await get_portfolio(db, portfolio_id)
    if row is None:
        raise NotFoundError("ScreenerPortfolio", str(portfolio_id))
    result = row.result or {}
    holdings = result.get("holdings") or []
    if not holdings:
        return JSONResponse(status_code=422, content={"error": "组合没有持仓记录"})

    tickers = [h.get("ticker") for h in holdings if h.get("ticker")]
    sub = (
        select(StockPrice.ticker, func.max(StockPrice.date).label("d"))
        .where(StockPrice.ticker.in_(tickers))
        .group_by(StockPrice.ticker)
        .subquery()
    )
    price_rows = (
        await db.execute(
            select(StockPrice.ticker, StockPrice.close).join(
                sub,
                and_(
                    StockPrice.ticker == sub.c.ticker,
                    StockPrice.date == sub.c.d,
                ),
            )
        )
    ).all()
    prices = {ticker: float(close) for ticker, close in price_rows if close is not None}

    computed = compute_rebalance(
        holdings,
        prices,
        cash=float(result.get("cash") or 0.0),
        tolerance=params.tolerance,
        lot_size=params.lot_size,
    )
    return {
        "portfolio_id": str(row.id),
        "name": row.name,
        **computed,
    }


@router.delete("/portfolios/{portfolio_id}", status_code=204)
async def remove_saved_portfolio(
    portfolio_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """删除已保存组合。"""
    if not await delete_portfolio(db, portfolio_id):
        raise NotFoundError("ScreenerPortfolio", str(portfolio_id))
    await db.commit()
