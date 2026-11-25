"""Scheduled screener run.

Default schedule runs the quant-only `core` preset daily after close. Configure with:
  SCREENER_SCHEDULE=30 16 * * 1-5
  SCREENER_SCHEDULE_PRESETS=core
"""

from __future__ import annotations

from sqlalchemy import select

from core.config import settings
from core.database import managed_session
from core.logging import logger

_ACTIVE = ("pending", "screening", "judging")


async def _run_one(db, preset, tag: str) -> dict:
    from screener.models import ScreenerRun
    from screener.service import run_screener, trigger_run

    active = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.status.in_(_ACTIVE)).limit(1))
    ).scalar_one_or_none()
    if active is not None:
        return {"status": "skipped", "reason": f"已有进行中的运行: {active.id}"}

    run = await trigger_run(
        db,
        {
            "mode": "presets",
            "pool": "all",
            "preset_ids": [str(preset.id)],
            "combine": "union",
        },
        enqueue=False,
    )
    if run is None:
        return {"status": "skipped", "reason": "触发被拒绝（可能有进行中的运行）"}

    done = await run_screener(db, run.id)
    if done.status != "completed":
        return {
            "status": done.status,
            "run_id": str(done.id),
            "error": done.error,
        }

    return {
        "status": "completed",
        "run_id": str(done.id),
        "candidate_count": done.candidate_count,
        "result_count": done.result_count,
    }


async def scheduled_screener_update() -> dict:
    """Run configured presets and persist a report for each."""
    from screener.models import CriteriaPreset

    tags = [
        tag.strip() for tag in (settings.SCREENER_SCHEDULE_PRESETS or "").split(",") if tag.strip()
    ]
    if not tags:
        return {"presets": {}, "message": "SCREENER_SCHEDULE_PRESETS 未配置"}

    results: dict[str, dict] = {}
    for tag in tags:
        async with managed_session() as db:
            preset = (
                await db.execute(
                    select(CriteriaPreset)
                    .where(
                        CriteriaPreset.style_tag == tag,
                        CriteriaPreset.is_active.is_(True),
                    )
                    .order_by(
                        CriteriaPreset.is_builtin.desc(),
                        CriteriaPreset.created_at,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if preset is None:
                results[tag] = {"status": "skipped", "reason": "未找到启用的预设"}
                continue
            try:
                results[tag] = await _run_one(db, preset, tag)
            except Exception as e:  # noqa: BLE001 — 单个预设失败不阻断其余
                # 失败仅记日志，不做任何推送
                logger.error("定时选股 %s 失败: %s", tag, e)
                results[tag] = {"status": "failed", "error": str(e)[:300]}

    return {"presets": results}


async def _handle_screener_schedule(payload: dict) -> dict:
    """持久任务 handler：手动“立即运行定时选股”走后台 worker。"""
    return await scheduled_screener_update()


from core.task_manager import register_handler  # noqa: E402

register_handler("screener_schedule", _handle_screener_schedule)
