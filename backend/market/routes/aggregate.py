"""Market Center API routes — aggregate of the per-domain routers.

Kept as a single import surface for backwards compatibility. Each
sub-domain now lives in its own module (price_routes, financial_routes,
profile_routes, news_routes, search_routes, freshness_routes).
"""

from __future__ import annotations

from fastapi import APIRouter

from market.routes.financial_routes import router as financial_router
from market.routes.freshness_routes import router as freshness_router
from market.routes.news_routes import router as news_router
from market.routes.price_routes import router as price_router
from market.routes.profile_routes import router as profile_router
from market.routes.search_routes import router as search_router

# Aggregate router — includes all sub-routers.
# The combined prefix lives on each sub-router ("/market"), so we include
# without an extra prefix here.
router = APIRouter(tags=["Market Center"])
router.include_router(price_router)
router.include_router(financial_router)
router.include_router(profile_router)
router.include_router(news_router)
router.include_router(search_router)
router.include_router(freshness_router)
