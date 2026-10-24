"""选股 → 研究中心的交接：为推荐股创建研究会话（默认不自动规划）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company
from research.models import ResearchSession
from research.session_service import SessionService
from screener.models import ScreenerJudgement, ScreenerRun

_HANDOFF_KEY = "screener_run_id"
_TICKER_KEY = "screener_ticker"


async def create_research_sessions(
    db: AsyncSession,
    run_id: uuid.UUID | str,
    tickers: list[str] | None = None,
    limit: int = 5,
) -> dict:
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == uuid.UUID(str(run_id))))
    ).scalar_one_or_none()
    if run is None:
        raise ValueError(f"运行不存在: {run_id}")

    rows = (
        await db.execute(
            select(ScreenerJudgement).where(
                ScreenerJudgement.run_id == run.id,
                ScreenerJudgement.status == "ok",
                ScreenerJudgement.recommend.is_(True),
            )
        )
    ).scalars().all()
    if tickers:
        wanted = {str(t) for t in tickers}
        rows = [j for j in rows if j.ticker in wanted]
    rows = sorted(rows, key=lambda j: j.confidence or 0.0, reverse=True)[:limit]

    companies = {
        c.ticker: c
        for c in (
            await db.execute(
                select(Company).where(Company.ticker.in_([j.ticker for j in rows]))
            )
        ).scalars().all()
    }

    existing = (
        await db.execute(
            select(ResearchSession).where(ResearchSession.extra_metadata.isnot(None))
        )
    ).scalars().all()
    existing_keys = {
        (s.extra_metadata.get(_HANDOFF_KEY), s.extra_metadata.get(_TICKER_KEY))
        for s in existing
        if s.extra_metadata
    }

    service = SessionService(db)
    created: list[dict] = []
    skipped: list[dict] = []
    for j in rows:
        key = (str(run.id), j.ticker)
        if key in existing_keys:
            skipped.append({"ticker": j.ticker, "name": j.name, "reason": "已创建过"})
            continue
        snapshot = j.snapshot or {}
        presets = snapshot.get("presets") or []
        context = (
            f"来源：智能选股 run {run.id}\n"
            f"选股标准：{run.criteria_text}\n"
            f"初筛得分：{snapshot.get('score')}；"
            f"命中预设：{'、'.join(presets) if presets else '-'}\n"
            f"选股报告：{run.report_path or '-'}"
        )
        session = await service.create(
            title=f"{j.name}（{j.ticker}）— 智能选股跟进",
            question=(
                f"评估 {j.name}（{j.ticker}）的投资价值："
                "核验智能选股命中的关键假设、主要风险与估值是否合理。"
            ),
            context=context,
            company_id=companies.get(j.ticker).id if companies.get(j.ticker) else None,
            tags=["screener", str(run.id)],
            auto_plan=False,
        )
        session.extra_metadata = {
            **(session.extra_metadata or {}),
            _HANDOFF_KEY: str(run.id),
            _TICKER_KEY: j.ticker,
        }
        created.append(
            {
                "session_id": str(session.id),
                "ticker": j.ticker,
                "name": j.name,
            }
        )
    await db.flush()
    return {
        "run_id": str(run.id),
        "created": created,
        "skipped": skipped,
        "requested": len(rows),
    }
