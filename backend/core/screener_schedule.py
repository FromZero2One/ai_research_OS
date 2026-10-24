"""Scheduled screener run + change report.

Default schedule runs the quant-only `core` preset daily after close and writes a
"what changed vs the previous same-preset run" Markdown report. Configure with:
  SCREENER_SCHEDULE=30 16 * * 1-5
  SCREENER_SCHEDULE_PRESETS=core
"""

from __future__ import annotations

from sqlalchemy import select

from core.config import settings
from core.database import managed_session
from core.event_service import EventLogger
from core.logging import logger

_ACTIVE = ("pending", "screening", "judging")


async def _run_one(db, preset, tag: str) -> dict:
    from screener.diff import diff_path_for
    from screener.diff_service import build_run_diff
    from screener.models import ScreenerRun
    from screener.service import run_screener, trigger_run

    active = (
        await db.execute(
            select(ScreenerRun).where(ScreenerRun.status.in_(_ACTIVE)).limit(1)
        )
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

    markdown, has_previous = await build_run_diff(db, done.id)
    path = diff_path_for(str(done.id))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    await EventLogger(db).record(
        source="screener",
        event_type="screener.diff",
        entity_type="screener_run",
        entity_id=str(done.id),
        summary=(
            f"定时选股 {preset.name}: 候选 {done.candidate_count}，"
            f"推荐 {done.result_count}，变化报告 {path.name}"
        ),
    )
    await db.commit()
    return {
        "status": "completed",
        "run_id": str(done.id),
        "candidate_count": done.candidate_count,
        "result_count": done.result_count,
        "diff_path": str(path),
        "has_previous": has_previous,
    }


async def scheduled_screener_update() -> dict:
    """Run configured presets and persist a change report for each."""
    from screener.models import CriteriaPreset

    tags = [
        tag.strip()
        for tag in (settings.SCREENER_SCHEDULE_PRESETS or "").split(",")
        if tag.strip()
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
                logger.warning("定时选股 %s 失败: %s", tag, e)
                results[tag] = {"status": "failed", "error": str(e)[:300]}

    return {"presets": results}
