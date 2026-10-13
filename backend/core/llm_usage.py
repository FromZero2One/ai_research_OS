"""LLM token 用量进程级累计器。

单用户本地工具，重启清零，不落库。按模型维度累计调用次数与
prompt/completion tokens，供 GET /ai/usage 汇总展示。
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime

_lock = threading.Lock()
# model -> {"calls", "prompt_tokens", "completion_tokens", "total_tokens",
#           "first_used", "last_used"}
_stats: dict[str, dict] = {}


def record_usage(model: str, usage: dict | None) -> None:
    """记录一次 LLM 调用的 usage（usage 为 None/缺 token 字段时跳过计数以外部分）。"""
    if not model:
        return
    now = datetime.now(UTC).isoformat()
    prompt = int(usage.get("prompt_tokens") or 0) if usage else 0
    completion = int(usage.get("completion_tokens") or 0) if usage else 0
    total = int(usage.get("total_tokens") or 0) if usage else 0
    if not total:
        total = prompt + completion

    with _lock:
        s = _stats.setdefault(
            model,
            {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
             "first_used": now, "last_used": now},
        )
        s["calls"] += 1
        s["prompt_tokens"] += prompt
        s["completion_tokens"] += completion
        s["total_tokens"] += total
        s["last_used"] = now


def get_usage_summary() -> dict:
    """返回按模型分组的用量汇总（字典副本，线程安全读取）。"""
    with _lock:
        models = {m: dict(s) for m, s in _stats.items()}
    return {
        "models": models,
        "totals": {
            "calls": sum(s["calls"] for s in models.values()),
            "prompt_tokens": sum(s["prompt_tokens"] for s in models.values()),
            "completion_tokens": sum(s["completion_tokens"] for s in models.values()),
            "total_tokens": sum(s["total_tokens"] for s in models.values()),
        },
        "note": "进程级统计，服务重启后清零",
    }
