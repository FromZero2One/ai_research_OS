"""Screener 推荐后表现 API — 收益查询、快照保存、历史。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.exceptions import NotFoundError
from screener.models import ScreenerRun
from screener.performance_service import build_run_performance
from screener.performance_store import (
    list_snapshots,
    save_snapshot,
    snapshot_json,
)

router = APIRouter(tags=["Screener"])


@router.get("/runs/{run_id}/performance")
async def get_performance(run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """推荐后表现：T+1 收盘买入，1/3/6/12 月等权收益与胜率。"""
    try:
        return await build_run_performance(db, run_id)
    except ValueError as e:
        raise NotFoundError("ScreenerRun", str(run_id)) from e


@router.post("/runs/{run_id}/performance/snapshot")
async def snapshot_performance(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """计算并保存当日表现快照（同一运行同一天幂等覆盖）。"""
    try:
        payload = await build_run_performance(db, run_id)
    except ValueError as e:
        raise NotFoundError("ScreenerRun", str(run_id)) from e
    row = await save_snapshot(db, run_id, payload)
    await db.commit()
    return snapshot_json(row)


@router.get("/runs/{run_id}/performance/history")
async def performance_history(
    run_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    """该运行的历史表现快照（按日期升序）。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
    ).scalar_one_or_none()
    if run is None:
        raise NotFoundError("ScreenerRun", str(run_id))
    rows = await list_snapshots(db, run_id)
    return {"snapshots": [snapshot_json(r) for r in rows]}
