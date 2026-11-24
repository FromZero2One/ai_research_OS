"""System utility routes — LLM token usage summary (migrated from deleted ai module)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/ai", tags=["System"])


@router.get("/usage")
async def get_llm_usage():
    """LLM token 用量汇总（进程级统计，重启清零）。"""
    from core.llm_usage import get_usage_summary

    return get_usage_summary()
