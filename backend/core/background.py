"""进程内后台协程助手（task_manager 持久队列退役后的直跑模式）。

幂等性不再依赖任务表：
- screener：`screener_runs` 上「同一时间仅一个进行中 run」的部分唯一索引兜底
- document：索引天然幂等（已索引文档重跑无副作用）

协程生命周期：强引用持有防 GC；异常在 done_callback 中显式取出并记日志
（fire-and-forget 语义，不向调用方传播）。
"""

from __future__ import annotations

import asyncio

from core.logging import logger

_BG_TASKS: set[asyncio.Task] = set()


def _on_done(task: asyncio.Task) -> None:
    _BG_TASKS.discard(task)
    if not task.cancelled() and task.exception() is not None:
        logger.error("Background task failed: %s", task.exception(), exc_info=task.exception())


def spawn_bg(coro) -> None:
    """Fire-and-forget：创建后台协程并持有强引用。"""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_on_done)
