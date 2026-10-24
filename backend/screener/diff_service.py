"""变化日报服务 — 查找同口径上一轮运行并生成 Markdown。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.diff import build_diff_markdown, compute_diff
from screener.models import ScreenerJudgement, ScreenerRun


def _run_dict(run: ScreenerRun) -> dict:
    return {
        "id": str(run.id),
        "created_at": run.created_at,
        "candidate_count": run.candidate_count,
        "result_count": run.result_count,
    }


def _judgement_dict(j: ScreenerJudgement) -> dict:
    return {
        "ticker": j.ticker,
        "name": j.name,
        "recommend": j.recommend,
        "status": j.status,
        "confidence": j.confidence,
        "snapshot": j.snapshot,
        "reasons": j.reasons,
        "criteria_hits": j.criteria_hits,
    }


async def _previous_run(db: AsyncSession, run: ScreenerRun) -> ScreenerRun | None:
    conditions = [
        ScreenerRun.id != run.id,
        ScreenerRun.status == "completed",
        ScreenerRun.created_at < run.created_at,
    ]
    if run.mode == "presets":
        conditions.extend(
            [
                ScreenerRun.mode == "presets",
                ScreenerRun.combine_mode == run.combine_mode,
                ScreenerRun.preset_ids == run.preset_ids,
            ]
        )
    else:
        conditions.extend(
            [
                ScreenerRun.mode.is_(None),
                ScreenerRun.criteria_hash == run.criteria_hash,
            ]
        )
    return (
        await db.execute(
            select(ScreenerRun)
            .where(*conditions)
            .order_by(ScreenerRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def build_run_diff(
    db: AsyncSession, run_id: uuid.UUID | str
) -> tuple[str, bool]:
    """返回 (Markdown, 是否存在上一轮基线)。运行不存在/未完成时给出说明文本。"""
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == uuid.UUID(str(run_id))))
    ).scalar_one_or_none()
    if run is None:
        raise ValueError(f"运行不存在: {run_id}")

    current = _run_dict(run)
    if run.status != "completed":
        return (
            build_diff_markdown(current, None, None).replace(
                "首次运行，暂无历史基线，下一轮开始可生成变化。",
                f"当前运行状态为 {run.status}，完成后再生成变化日报。",
            ),
            False,
        )

    previous = await _previous_run(db, run)
    if previous is None:
        return build_diff_markdown(current, None, None), False

    judgements = (
        await db.execute(
            select(ScreenerJudgement).where(
                ScreenerJudgement.run_id.in_([run.id, previous.id])
            )
        )
    ).scalars().all()
    current_js = [_judgement_dict(j) for j in judgements if j.run_id == run.id]
    previous_js = [_judgement_dict(j) for j in judgements if j.run_id == previous.id]

    diff = compute_diff(current_js, previous_js)
    return build_diff_markdown(current, _run_dict(previous), diff), True
