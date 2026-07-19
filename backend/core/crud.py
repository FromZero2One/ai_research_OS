"""Reusable CRUD base for common patterns."""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func

from core.base import Base
from core.exceptions import NotFoundError

ModelT = TypeVar("ModelT", bound=Base)


class CRUDBase(Generic[ModelT]):
    """Generic CRUD with common query patterns."""

    def __init__(self, model: type[ModelT], session: AsyncSession) -> None:
        self.model = model
        self.session = session

    async def get(self, id: UUID) -> ModelT:
        result = await self.session.execute(
            select(self.model).where(self.model.id == id)  # type: ignore[attr-defined]
        )
        obj = result.scalar_one_or_none()
        if not obj:
            raise NotFoundError(self.model.__name__, str(id))
        return obj

    async def list(
        self, skip: int = 0, limit: int = 100, **filters
    ) -> tuple[list[ModelT], int]:
        stmt = select(self.model)

        for col, val in filters.items():
            if val is not None:
                col_attr = getattr(self.model, col, None)
                if col_attr is not None:
                    stmt = stmt.where(col_attr == val)

        # Count
        count_stmt = stmt.with_only_columns(func.count()).order_by(None)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total

    async def create(self, **kwargs) -> ModelT:
        obj = self.model(**kwargs)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, id: UUID, **kwargs) -> ModelT:
        obj = await self.get(id)
        for key, val in kwargs.items():
            if val is not None:
                setattr(obj, key, val)
        await self.session.flush()
        return obj

    async def delete(self, id: UUID) -> None:
        obj = await self.get(id)
        await self.session.delete(obj)
