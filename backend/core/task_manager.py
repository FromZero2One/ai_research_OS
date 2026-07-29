"""Persistent background task system — TaskRecord table + worker loop.

Replaces the old in-memory set (weakref Set) with:
  - PostgreSQL-backed TaskRecord table
  - Auto-retry with configurable max_attempts
  - Dedup by (task_type, task_key) for running/pending tasks
  - Startup recovery: re-queue incomplete tasks on boot
  - REST API for status monitoring

Usage:
    from core.task_manager import create_task, register_handler

    # Register a handler (at import time)
    register_handler("quick_research", run_quick_research)

    # Fire a background task (returns immediately, runs in worker)
    task = await create_task("quick_research", session_id, {...})
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from sqlalchemy import DateTime, Integer, String, Text, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID as UUIDType
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from core.base import Base, UUIDMixin, TimestampMixin
from core.logging import logger

# ── Task Record Model ─────────────────────────────────────────────────────


class TaskRecord(Base, UUIDMixin, TimestampMixin):
    """Persistent background task — survives process restart."""

    __tablename__ = "task_records"
    __table_args__ = {"schema": "core"}

    task_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """Logical type — maps to a registered handler function."""

    task_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    """Unique key per (type, active) — used for dedup (e.g. session_id string)."""

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", index=True)
    """pending → running → completed | failed"""

    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Arguments passed to the handler."""

    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """Handler return value."""

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Error message if failed."""

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ── Handler Registry ──────────────────────────────────────────────────────

HandlerFn = Callable[[dict, AsyncSession], Coroutine[Any, Any, dict | None]]

_task_handlers: dict[str, HandlerFn] = {}


def register_handler(task_type: str, fn: HandlerFn) -> None:
    """Register a handler function for a task type.

    The handler receives (payload: dict, session: AsyncSession) and
    returns a dict (stored as TaskRecord.result) or None.
    """
    _task_handlers[task_type] = fn
    logger.debug("Task handler registered: %s", task_type)


# ── Task CRUD ─────────────────────────────────────────────────────────────


async def create_task(
    task_type: str,
    task_key: str,
    payload: dict | None = None,
    max_attempts: int = 3,
    db: AsyncSession | None = None,
) -> TaskRecord | None:
    """Create a background task. Returns None if duplicate (already pending/running)."""
    from core.database import managed_session

    async def _do(session: AsyncSession) -> TaskRecord | None:
        # Dedup: reject if same (type, key) already pending or running
        existing = await session.execute(
            select(TaskRecord).where(
                TaskRecord.task_type == task_type,
                TaskRecord.task_key == task_key,
                TaskRecord.status.in_(["pending", "running"]),
            ).limit(1)
        )
        if existing.scalar_one_or_none():
            logger.debug("Task %s/%s already active — skipping", task_type, task_key)
            return None

        task = TaskRecord(
            task_type=task_type,
            task_key=task_key,
            payload=payload or {},
            max_attempts=max_attempts,
            scheduled_at=datetime.now(timezone.utc),
        )
        session.add(task)
        await session.flush()
        logger.info("Task created: %s/%s (id=%s)", task_type, task_key, task.id)
        return task

    if db is not None:
        return await _do(db)
    async with managed_session() as session:
        return await _do(session)


async def get_task(task_id: uuid.UUID, db: AsyncSession) -> TaskRecord | None:
    result = await db.execute(
        select(TaskRecord).where(TaskRecord.id == task_id)
    )
    return result.scalar_one_or_none()


async def list_tasks(
    task_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db: AsyncSession | None = None,
) -> list[TaskRecord]:
    from core.database import managed_session

    async def _do(session: AsyncSession) -> list[TaskRecord]:
        stmt = select(TaskRecord).order_by(TaskRecord.scheduled_at.desc()).limit(limit)
        if task_type:
            stmt = stmt.where(TaskRecord.task_type == task_type)
        if status:
            stmt = stmt.where(TaskRecord.status == status)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    if db is not None:
        return await _do(db)
    async with managed_session() as session:
        return await _do(session)


async def retry_task(task_id: uuid.UUID, db: AsyncSession) -> TaskRecord | None:
    """Reset a failed task to pending so the worker picks it up again."""
    task = await get_task(task_id, db)
    if task and task.status == "failed":
        task.status = "pending"
        task.error = None
        task.attempts = 0
        await db.flush()
        logger.info("Task %s reset for retry", task_id)
    return task


# ── Worker ────────────────────────────────────────────────────────────────

_task_worker_running = False


async def _recover_interrupted_tasks() -> None:
    """On startup: reset running tasks to pending so they get retried."""
    from core.database import managed_session

    async with managed_session() as session:
        result = await session.execute(
            select(TaskRecord).where(
                TaskRecord.status.in_(["running"]),
            )
        )
        interrupted = list(result.scalars().all())
        for task in interrupted:
            task.status = "pending"
            task.error = f"Interrupted by server restart (attempt {task.attempts}/{task.max_attempts})"
            logger.warning("  [tasks] recovered interrupted task %s (%s/%s)", task.id, task.task_type, task.task_key)
        if interrupted:
            await session.commit()
            logger.info("  [tasks] recovered %d interrupted task(s)", len(interrupted))


async def _task_worker_loop() -> None:
    """Background loop: poll for pending tasks and execute them."""
    global _task_worker_running
    from core.database import managed_session

    _task_worker_running = True
    logger.info("  [tasks] worker loop started")

    while _task_worker_running:
        try:
            async with managed_session() as session:
                # Pick next pending task (FIFO by scheduled_at)
                result = await session.execute(
                    select(TaskRecord)
                    .where(
                        TaskRecord.status == "pending",
                        TaskRecord.scheduled_at <= datetime.now(timezone.utc),
                        TaskRecord.attempts < TaskRecord.max_attempts,
                    )
                    .order_by(TaskRecord.scheduled_at)
                    .limit(1)
                )
                task = result.scalar_one_or_none()

                if task is None:
                    await asyncio.sleep(1)
                    continue

                # Mark as running
                task.status = "running"
                task.attempts += 1
                task.started_at = datetime.now(timezone.utc)
                await session.commit()

            # Execute outside the pick-transaction (handler has its own session)
            await _execute_task(task)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error("  [tasks] worker error: %s", e, exc_info=True)
            await asyncio.sleep(5)

    logger.info("  [tasks] worker loop stopped")


async def _execute_task(task: TaskRecord) -> None:
    """Execute a single task by dispatching to its registered handler."""
    import asyncio
    from core.database import managed_session

    handler = _task_handlers.get(task.task_type)
    if not handler:
        async with managed_session() as session:
            task_in_db = await session.get(TaskRecord, task.id)
            if task_in_db:
                task_in_db.status = "failed"
                task_in_db.error = f"No handler registered for task_type: {task.task_type}"
                task_in_db.completed_at = datetime.now(timezone.utc)
            return

    logger.info("  [tasks] executing %s/%s (attempt %d/%d)", task.task_type, task.task_key, task.attempts, task.max_attempts)
    try:
        # Handlers receive payload and create their own managed_session internally
        result = await handler(task.payload or {})
    except Exception as e:
        async with managed_session() as session:
            task_in_db = await session.get(TaskRecord, task.id)
            if not task_in_db:
                return
            task_in_db.error = f"{type(e).__name__}: {e}"
            task_in_db.completed_at = datetime.now(timezone.utc)
            if task_in_db.attempts >= task_in_db.max_attempts:
                task_in_db.status = "failed"
                logger.error("  [tasks] %s/%s FAILED after %d attempts: %s",
                             task.task_type, task.task_key, task.attempts, e)
            else:
                task_in_db.status = "pending"  # will retry
                logger.warning("  [tasks] %s/%s failed (attempt %d/%d), will retry: %s",
                               task.task_type, task.task_key, task.attempts, task.max_attempts, e)
        return

    # Success
    async with managed_session() as session:
        task_in_db = await session.get(TaskRecord, task.id)
        if task_in_db:
            task_in_db.status = "completed"
            task_in_db.result = result if isinstance(result, dict) else {"status": "ok"}
            task_in_db.completed_at = datetime.now(timezone.utc)
            logger.info("  [tasks] %s/%s completed", task.task_type, task.task_key)


def stop_worker() -> None:
    """Signal the worker loop to stop."""
    global _task_worker_running
    _task_worker_running = False


# ── Convenience: background wrapper ──────────────────────────────────────


async def run_in_background(
    task_type: str,
    task_key: str,
    payload: dict | None = None,
) -> bool:
    """Fire-and-forget: create a persistent task. Returns True if created."""
    task = await create_task(task_type, task_key, payload)
    return task is not None


import asyncio  # noqa: E402 (needed for sleep above)
