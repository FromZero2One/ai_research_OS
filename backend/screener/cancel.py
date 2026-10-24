"""运行取消信号 — 进程内事件（API 与后台 worker 同进程）。

DB 状态仍是唯一事实源（排队中的 run 由 worker 启动时检查），
事件只用于让正在执行的流水线/深判在下一个检查点尽快停下。
"""

from __future__ import annotations

import asyncio
import uuid

_EVENTS: dict[str, asyncio.Event] = {}


def _key(run_id: uuid.UUID | str) -> str:
    return str(run_id)


def request_cancel(run_id: uuid.UUID | str) -> None:
    _EVENTS.setdefault(_key(run_id), asyncio.Event()).set()


def is_cancelled(run_id: uuid.UUID | str) -> bool:
    event = _EVENTS.get(_key(run_id))
    return event is not None and event.is_set()


def clear_cancel(run_id: uuid.UUID | str) -> None:
    _EVENTS.pop(_key(run_id), None)
