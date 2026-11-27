"""FastAPI application factory — wires all modules, middleware, and lifecycle."""

# Imports below are deliberately ordered: proxy env must be stripped before
# any httpx-dependent module is imported, and models must be registered
# before routers resolve services lazily.
# ruff: noqa: E402

from __future__ import annotations

# ── Strip proxy BEFORE any httpx import ──────────────────────────
# httpx caches proxy config at its own import time, so this must
# run before any adapter module is loaded.
from core.proxy_cleanup import clean_proxy_env

clean_proxy_env()
# ─────────────────────────────────────────────────────────────────

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── Register all ORM models ────────────────────────────────────────────
# Routers resolve services lazily via the DI container. company/market/screener
# models are imported explicitly here; core.event_log / document.models reach
# Base.metadata via transitive imports (routes → container → services) — the
# test suite's create_all verifies the set is complete. Keep the explicit list
# in sync with alembic/env.py when adding modules.
import company.models  # noqa: F401  # 注册模型到 Base.metadata
import market.models  # noqa: F401
import screener.models  # noqa: F401
from company.routes import router as company_router
from core.config import settings
from core.exceptions import (
    AIResearchOSError,
    AuthenticationError,
    AuthorizationError,
    DomainError,
    DuplicateError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from core.logging import configure_logging, logger
from core.scheduler_routes import router as scheduler_router
from document.routes import router as document_router

from market.routes.financial_routes import router as market_financial_router
from market.routes.freshness_routes import router as market_freshness_router
from market.routes.price_routes import router as market_price_router
from market.routes.search_routes import router as market_search_router
from screener.routes import router as screener_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifecycle — startup / shutdown."""
    configure_logging()
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Startup: verify DB connection, create vector collections, schedule jobs
    from core.adapters.embedding import create_embedding
    from core.database import async_session_factory, engine

    try:
        async with engine.connect() as conn:
            await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        logger.info("Database connection verified")
    except Exception as e:
        logger.warning("Database not available at startup: %s", e)

    # Pre-warm embedding model (lazy — runs in background, doesn't block startup)
    if settings.EMBEDDING_PREWARM:
        try:
            embedder = create_embedding()
            _ = await embedder.embed(["warmup"])
            logger.info("Embedding model ready: dim=%d", embedder.dimension)
        except Exception as e:
            logger.debug("Embedding model lazy-load deferred: %s", e)

    # DI container — routes use `request.app.state.container` or the
    # `get_container` dependency to resolve services.
    from core.container import create_container

    app.state.container_factory = create_container
    app.state.engine = engine
    app.state.session_factory = async_session_factory

    # Start scheduler
    if settings.SCHEDULER_ENABLED:
        from core.financial_sync import financial_data_update
        from core.market_sync import market_data_update
        from core.scheduler import register_job, start_scheduler
        from core.screener_schedule import scheduled_screener_update

        register_job("market_data_update", market_data_update)
        register_job("financial_data_update", financial_data_update)
        register_job("screener_schedule", scheduled_screener_update)
        start_scheduler()
        logger.info("Scheduler started (enabled=%s)", settings.SCHEDULER_ENABLED)
    else:
        logger.info("Scheduler disabled via config")

    yield

    # Shutdown
    logger.info("Shutting down %s", settings.APP_NAME)
    from core.scheduler import stop_scheduler

    stop_scheduler()
    await engine.dispose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if settings.ENV != "production" else None,
        redoc_url="/redoc" if settings.ENV != "production" else None,
    )

    # ── Middleware ────────────────────────────────────────────────

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        logger.info("%s %s", request.method, request.url.path)
        response = await call_next(request)
        return response

    # ── Exception handlers ────────────────────────────────────────

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError):
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "detail": str(exc),
                "resource": exc.resource,
                "id": exc.id,
            },
        )

    @app.exception_handler(ValidationError)
    async def validation_handler(request: Request, exc: ValidationError):
        return JSONResponse(
            status_code=422,
            content={"error": "validation_error", "detail": str(exc)},
        )

    @app.exception_handler(DuplicateError)
    async def duplicate_handler(request: Request, exc: DuplicateError):
        return JSONResponse(
            status_code=409,
            content={"error": "duplicate", "detail": str(exc)},
        )

    @app.exception_handler(AuthenticationError)
    async def auth_handler(request: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=401,
            content={"error": "unauthorized", "detail": str(exc)},
        )

    @app.exception_handler(AuthorizationError)
    async def permission_handler(request: Request, exc: AuthorizationError):
        return JSONResponse(
            status_code=403,
            content={"error": "forbidden", "detail": str(exc)},
        )

    @app.exception_handler(ExternalServiceError)
    async def external_handler(request: Request, exc: ExternalServiceError):
        return JSONResponse(
            status_code=502,
            content={
                "error": "external_service_error",
                "service": exc.service,
                "detail": str(exc),
            },
        )

    @app.exception_handler(AIResearchOSError)
    async def base_handler(request: Request, exc: AIResearchOSError):
        return JSONResponse(
            status_code=500,
            content={"error": "internal_error", "detail": str(exc)},
        )

    @app.exception_handler(DomainError)
    async def domain_handler(request: Request, exc: DomainError):
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": "domain_error", "detail": exc.detail},
        )

    # ── Health ────────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "env": settings.ENV,
        }

    # ── Register module routers ───────────────────────────────────

    app.include_router(company_router, prefix="/api/v1")
    app.include_router(market_price_router, prefix="/api/v1")
    app.include_router(market_financial_router, prefix="/api/v1")
    app.include_router(market_search_router, prefix="/api/v1")
    app.include_router(market_freshness_router, prefix="/api/v1")
    app.include_router(document_router, prefix="/api/v1")
    app.include_router(scheduler_router, prefix="/api/v1")
    app.include_router(screener_router, prefix="/api/v1")

    return app


# Module-level app for `uvicorn api.app:app`
app = create_app()
