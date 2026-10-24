"""变化日报服务 — 查找同口径上一轮运行并生成 Markdown。"""

from __future__ import annotations

import hashlib
import json
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


def rules_signature(run: ScreenerRun) -> str:
    """实际生效规则的结构指纹（用于确认两轮筛选口径一致）。

    预设被编辑后 preset_ids 不变，仅靠 ids 会把旧规则运行误当基线；
    这里对 run.rules 做稳定哈希。`preset_names` 只影响展示，不参与。
    """
    rules = dict(run.rules or {})
    rules.pop("preset_names", None)
    payload = json.dumps(rules, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def _previous_run(
    db: AsyncSession, run: ScreenerRun
) -> tuple[ScreenerRun | None, bool]:
    """最近一轮同口径运行 + 是否存在“同 ids 但规则已变”的旧运行。"""
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
    candidates = (
        await db.execute(
            select(ScreenerRun)
            .where(*conditions)
            .order_by(ScreenerRun.created_at.desc())
            .limit(20)
        )
    ).scalars().all()
    current_sig = rules_signature(run)
    for previous in candidates:
        if rules_signature(previous) == current_sig:
            return previous, False
    # 有历史运行但规则指纹全部不一致 → 不能作为变化基线
    return None, bool(candidates)


async def build_run_diff(
    db: AsyncSession, run_id: uuid.UUID | str
) -> tuple[str, bool]:
    """返回 (Markdown, 是否存在上一轮基线)。运行不存在/未完成时给出说明文本。"""
    markdown, has_previous, _ = await build_run_diff_data(db, run_id)
    return markdown, has_previous


async def build_run_diff_data(
    db: AsyncSession, run_id: uuid.UUID | str
) -> tuple[str, bool, dict | None]:
    """返回 (Markdown, 是否存在上一轮基线, 变化详情)。无基线/未完成时详情为 None。"""
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
            None,
        )

    previous, rules_changed = await _previous_run(db, run)
    if previous is None:
        markdown = build_diff_markdown(current, None, None)
        if rules_changed:
            markdown = markdown.replace("无（首次运行）", "无（规则已变更）")
            markdown = markdown.replace(
                "首次运行，暂无历史基线，下一轮开始可生成变化。",
                "同口径预设的规则已变更，历史运行不可比；本轮作为新基线，"
                "下一轮开始生成变化。",
            )
        return markdown, False, None

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
    return build_diff_markdown(current, _run_dict(previous), diff), True, diff
