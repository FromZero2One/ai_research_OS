"""Test fixtures — sync + async TestClient, per-test table cleanup.

Tests run against a dedicated database (default ``airesearch_test``), never
the development database: the per-test TRUNCATE would destroy real data.
The test DB is created and migrated on first use; a guard refuses to run
if the resolved test URL points at the same database as the dev URL.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from api.app import create_app
from core.config import settings

import screener.models  # noqa: F401  # 尚未挂载路由，需显式导入以注册到 Base.metadata
from core.container import Container
from core.database import get_container, get_db

# Tests don't need a real embedding model — skip the 20-30s startup warmup.
settings.EMBEDDING_PREWARM = False

# Isolate tests from the development Qdrant collection: uploaded vectors and
# searches must never touch the dev "documents" collection (which accumulates
# stale points across runs and crowds out fresh results).
settings.QDRANT_COLLECTION = "documents_test"

# ── Dedicated test database ─────────────────────────────────────────────

TEST_DB_NAME = os.getenv("TEST_DATABASE_NAME", "airesearch_test")
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    default=f"{settings.DATABASE_URL.rsplit('/', 1)[0]}/{TEST_DB_NAME}",
)


def _db_name(url: str) -> str:
    """Extract the database name from a SQLAlchemy URL."""
    return url.rstrip("/").rsplit("/", 1)[-1].split("?")[0]


if _db_name(TEST_DATABASE_URL) == _db_name(settings.DATABASE_URL):
    raise RuntimeError(
        "Refusing to run tests against the development database "
        f"({settings.DATABASE_URL!r}). Set TEST_DATABASE_URL (or "
        "TEST_DATABASE_NAME) to a dedicated test database."
    )


def _sync(url: str) -> str:
    """Convert an asyncpg URL to the psycopg2 dialect used by sync engines."""
    return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")


def _ensure_test_db() -> None:
    """Idempotently create the test database, extensions, and schema."""
    from core.base import Base

    # 1. Create the database if missing (via the postgres maintenance DB).
    admin_url = _sync(f"{settings.DATABASE_URL.rsplit('/', 1)[0]}/postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": TEST_DB_NAME},
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB_NAME}"'))
    admin_engine.dispose()

    # 2. Extensions + schemas (models reference e.g. company.* / ai.*) then
    #    create tables. Models are already registered on Base.metadata by the
    #    `from api.app import create_app` import above.
    test_engine = create_engine(_sync(TEST_DATABASE_URL), pool_pre_ping=True)
    with test_engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        for schema in (
            "company",
            "market",
            "document",
            "knowledge",
            "ai",
            "research",
            "portfolio",
            "screener",
            "core",
            "akshare",
        ):
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    Base.metadata.create_all(test_engine)
    # 预设库内置种子（测试库不跑 alembic，与迁移共用唯一事实源）
    from screener.seeds import insert_builtin_seeds

    with test_engine.begin() as conn:
        insert_builtin_seeds(conn)
    test_engine.dispose()


_ensure_test_db()


@pytest.fixture(scope="session", autouse=True)
def _clean_test_qdrant_collection():
    """Drop the test-only Qdrant collection before the session starts.

    Without this, points uploaded by previous test runs linger in Qdrant and
    crowd out freshly indexed chunks from the top-k dense results.
    """
    import asyncio

    from qdrant_client import AsyncQdrantClient

    async def _drop() -> None:
        client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
        )
        try:
            collections = await client.get_collections()
            names = {c.name for c in collections.collections}
            if settings.QDRANT_COLLECTION in names:
                await client.delete_collection(settings.QDRANT_COLLECTION)
        finally:
            await client.close()

    asyncio.run(_drop())
    yield


# ── Test async engine with NullPool (avoids asyncpg event-loop conflict) ─

test_async_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool,
)


async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
    """Test DB dependency — commit after each request, rollback on error."""
    async with test_async_engine.connect() as conn:
        session = AsyncSession(bind=conn, expire_on_commit=False)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def _get_test_container() -> AsyncGenerator[Container, None]:
    """Test DI container bound to the per-test NullPool session.

    Containerized routes depend on ``get_container``, which internally builds
    on the shared pooled engine — connections created inside Starlette's
    TestClient loop then get reused by async tests running in pytest's loop
    (and vice versa), producing "Event loop is closed" failures. Overriding
    the container keeps every request on the isolated test session instead.
    """
    from core.container import create_container

    async for session in _get_test_db():
        yield create_container(session)


# ── Synchronous engine for table cleanup ───────────────────────────────

sync_url = _sync(TEST_DATABASE_URL)
cleanup_engine = create_engine(sync_url, pool_pre_ping=True)


ALL_TABLES = [
    "company.companies",
    "company.company_tags",
    "market.stock_prices",
    "market.financial_metrics",
    "market.data_freshness",
    "market.valuation_history",
    "market.stock_industry",
    "document.documents",
    "document.document_chunks",
    "ai.prompt_templates",
    "research.research_sessions",
    "research.research_evidences",
    "research.research_reports",
    "portfolio.holdings",
    "portfolio.investment_journal",
    "core.event_log",
    "screener.screener_judgements",
    "screener.screener_runs",
    "screener.screener_rules",
    "screener.backtest_runs",
    "screener.portfolios",
]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    """Clear proxy env vars that break httpx/TestClient."""
    for var in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _disable_background_tasks(monkeypatch: pytest.MonkeyPatch):
    """Stub background task dispatch in tests.

    Real tasks would write TaskRecords to the dev database and touch a second
    event loop — none of which runs here (the worker isn't part of tests).
    """

    async def _noop(task_type: str, task_key: str, payload: dict | None = None) -> bool:
        return True

    monkeypatch.setattr("document.routes.run_in_background", _noop)


@pytest.fixture(autouse=True)
def _isolate_screener_spot_cache(monkeypatch: pytest.MonkeyPatch):
    """Don't write test snapshots into the shared dev Redis cache.

    The screener spot cache key is date-based, so a test snapshot (1-2 rows)
    would poison real screens for the rest of the day.
    """
    from screener import screening

    class _NoopCache:
        async def get(self, key: str):
            return None

        async def set(self, key: str, value: str, ttl: int | None = None) -> None:
            return None

    monkeypatch.setattr(screening, "_get_cache", lambda: _NoopCache())


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all project tables before each test.

    Runs in setup (before the app/test starts) so no app-held DB
    transactions/locks can block the TRUNCATE.
    """
    with cleanup_engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
        conn.execute(text("SET lock_timeout = '5s'"))
        tables = ", ".join(ALL_TABLES)
        conn.execute(text(f"TRUNCATE TABLE {tables} CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))
    yield


@pytest.fixture
def client() -> TestClient:
    """FastAPI synchronous test client with NullPool DB override."""
    app = create_app()
    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_container] = _get_test_container
    with TestClient(app) as c:
        yield c


@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    """Async ASGI client — ignores proxy env vars (ALL_PROXY breaks httpx)."""
    app = create_app()
    app.dependency_overrides[get_db] = _get_test_db
    app.dependency_overrides[get_container] = _get_test_container
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        trust_env=False,
    ) as ac:
        yield ac


@pytest.fixture
async def test_session() -> AsyncGenerator[AsyncSession, None]:
    """Test DB session bound to the isolated test engine — for direct service calls."""
    async for session in _get_test_db():
        yield session


# ── Sample data helpers ───────────────────────────────────────────────

SAMPLE_COMPANY = {
    "ticker": "TEST",
    "name": "Test Corp",
    "description": "A test company for unit testing",
    "sector": "Technology",
    "industry": "Software",
    "headquarters": "Testville, TX",
    "founded_year": 2020,
    "employees": 100,
    "website": "https://testcorp.example",
    "tags": ["tech", "test"],
}

SAMPLE_RESEARCH = {
    "title": "Test Research Session",
    "question": "Is this a good test?",
    "context": "Testing the research workflow",
    "auto_plan": False,
}

SAMPLE_PROMPT_TEMPLATE = {
    "name": "test-summarizer",
    "description": "Test template",
    "system_prompt": "You are a test assistant.",
    "user_prompt_template": "Summarize: {text}",
    "temperature": 0.3,
    "max_tokens": 500,
}
