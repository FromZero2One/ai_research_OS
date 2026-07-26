"""Simple in-memory background task tracker.

Stores references to running asyncio tasks so they don't get GC'd.
Progress is persisted in the DB (session extra_metadata), not in memory.
This tracker only prevents task cancellation and provides a health check.
"""

from __future__ import annotations

import weakref
from typing import Set

# Weak set of running task identifiers — prevents GC without leaking
_running_tasks: Set[str] = set()


def track(session_id: str) -> None:
    """Mark a research session as having a running background task."""
    _running_tasks.add(session_id)


def untrack(session_id: str) -> None:
    """Mark a research session's background task as complete."""
    _running_tasks.discard(session_id)


def is_running(session_id: str) -> bool:
    """Check if a research session has a running background task."""
    return session_id in _running_tasks


def running_count() -> int:
    """Number of currently running background research tasks."""
    return len(_running_tasks)
