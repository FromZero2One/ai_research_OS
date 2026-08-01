"""Async SQLAlchemy engine, session factory, and dependency.

Usage:
    # FastAPI route (automatic commit/rollback via dependency injection)
    @router.get(...)
    async def handler(db: AsyncSession = Depends(get_db)): ...

    # Background task (use managed_session for safe commit/rollback)
    async with managed_session() as db:
        ...  # auto-committed on success, rolled back on error
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import settings

if TYPE_CHECKING:
    from core.container import Container

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DATABASE_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async DB session.

    The session is committed after the response is sent.
    If the handler raises, the session is rolled back.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_container() -> AsyncGenerator[Container, None]:
    """FastAPI dependency that yields a DI container for the request.

    Builds on top of ``get_db`` so the session is managed automatically.
    """
    from core.container import create_container

    async for session in get_db():
        yield create_container(session)


@asynccontextmanager
async def managed_session() -> AsyncIterator[AsyncSession]:
    """Safe session lifecycle for background tasks.

    Auto-commits on success, rolls back on error, always closes.
    Use this instead of ``async_session_factory()`` directly.
    """
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
