"""FastAPI application factory — wires all modules, middleware, and lifecycle."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.config import settings
from core.exceptions import (
    AIResearchOSError,
    AuthenticationError,
    AuthorizationError,
    DuplicateError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)
from core.logging import configure_logging, logger

# ── Module routers ──────────────────────────────────────────────────

from ai.routes import router as ai_router
from company.routes import router as company_router
from core.scheduler_routes import router as scheduler_router
from dashboard.routes import router as dashboard_router
from document.routes import router as document_router
from knowledge.routes import router as knowledge_router
from market.routes import router as market_router
from portfolio.routes import router as portfolio_router
from research.quick import router as quick_research_router
from research.routes import router as research_router
from research.timeline import router as research_timeline_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifecycle — startup / shutdown."""
    configure_logging()
    logger.info("Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)

    # Startup: verify DB connection, create vector collections, schedule jobs
    from core.adapters.embedding import create_embedding
    from core.adapters.vector_store import create_vector_store
    from core.database import engine

    try:
        async with engine.connect() as conn:
            await conn.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        logger.info("Database connection verified")
    except Exception as e:
        logger.warning("Database not available at startup: %s", e)

    # Pre-warm embedding model (lazy — runs in background, doesn't block startup)
    try:
        embedder = create_embedding()
        _ = embedder.dimension
        logger.info("Embedding model ready: dim=%d", embedder.dimension)
    except Exception as e:
        logger.debug("Embedding model lazy-load deferred: %s", e)

    # Start scheduler
    if settings.SCHEDULER_ENABLED:
        from core.scheduler import start_scheduler
        from core.scheduler import register_job
        from core.scheduler_jobs import market_data_update, morning_brief
        from core.observation_engine import run_observation_cycle

        register_job("market_data_update", market_data_update)
        register_job("morning_brief", morning_brief)
        register_job("observation_cycle", run_observation_cycle)
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
    app.include_router(market_router, prefix="/api/v1")
    app.include_router(document_router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(research_router, prefix="/api/v1")
    app.include_router(portfolio_router, prefix="/api/v1")
    app.include_router(scheduler_router, prefix="/api/v1")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(quick_research_router, prefix="/api/v1")
    app.include_router(research_timeline_router, prefix="/api/v1")

    return app


# Module-level app for `uvicorn api.app:app`
app = create_app()
