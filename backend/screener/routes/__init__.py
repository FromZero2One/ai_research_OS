"""Screener API 聚合路由 — 按领域拆分到子模块，对外仍导出单个 ``router``。"""

from __future__ import annotations

from fastapi import APIRouter

from screener.routes.backtest import router as backtest_router
from screener.routes.criteria import router as criteria_router
from screener.routes.performance import router as performance_router
from screener.routes.portfolio import router as portfolio_router
from screener.routes.presets import router as presets_router
from screener.routes.runs import router as runs_router

router = APIRouter(prefix="/screener", tags=["Screener"])
router.include_router(runs_router)
router.include_router(backtest_router)
router.include_router(presets_router)
router.include_router(criteria_router)
router.include_router(portfolio_router)
router.include_router(performance_router)
