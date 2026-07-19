"""Test fixtures — synchronous TestClient + per-test table cleanup."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from api.app import create_app
from core.config import settings
from core.database import get_db

# ── Test async engine with NullPool (avoids asyncpg event-loop conflict) ─

test_async_engine = create_async_engine(
    settings.DATABASE_URL,
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


# ── Synchronous engine for table cleanup ───────────────────────────────

sync_url = settings.DATABASE_URL.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)
cleanup_engine = create_engine(sync_url, pool_pre_ping=True)


ALL_TABLES = [
    "company.companies", "company.company_tags",
    "market.stock_prices", "market.financial_metrics", "market.macro_indicators",
    "document.documents", "document.document_chunks",
    "ai.prompt_templates", "ai.ai_workflows",
    "research.research_sessions", "research.research_evidences", "research.research_reports",
    "portfolio.watchlists", "portfolio.watchlist_items", "portfolio.holdings", "portfolio.investment_journal",
    "core.event_log",
]


@pytest.fixture(autouse=True)
def clean_tables():
    """Truncate all project tables after each test."""
    yield
    with cleanup_engine.begin() as conn:
        conn.execute(text("SET session_replication_role = 'replica'"))
        for table in ALL_TABLES:
            conn.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))


@pytest.fixture
def client() -> TestClient:
    """FastAPI synchronous test client with NullPool DB override."""
    app = create_app()
    app.dependency_overrides[get_db] = _get_test_db
    return TestClient(app)


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
}

SAMPLE_PROMPT_TEMPLATE = {
    "name": "test-summarizer",
    "description": "Test template",
    "system_prompt": "You are a test assistant.",
    "user_prompt_template": "Summarize: {text}",
    "temperature": 0.3,
    "max_tokens": 500,
}
