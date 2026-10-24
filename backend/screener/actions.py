"""选股结果的后续动作 — 加入自选（Company.is_active）。"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from company.models import Company
from core.event_service import EventLogger
from screener.models import ScreenerJudgement, ScreenerRun


async def add_to_watchlist(
    db: AsyncSession,
    run_id: uuid.UUID,
    tickers: list[str] | None = None,
    limit: int = 50,
) -> dict:
    """把该轮推荐股（或指定 ticker）加入自选（is_active=True）。

    只处理有 Company 记录的票；重复加入幂等。缺少的公司放入 missing。
    """
    run = (
        await db.execute(select(ScreenerRun).where(ScreenerRun.id == run_id))
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
    if not rows:
        return {
            "run_id": str(run.id),
            "added": [],
            "already": [],
            "missing": [],
        }

    companies = {
        c.ticker: c
        for c in (
            await db.execute(
                select(Company).where(Company.ticker.in_([j.ticker for j in rows]))
            )
        ).scalars().all()
    }
    added: list[dict] = []
    already: list[dict] = []
    missing: list[dict] = []
    for j in rows:
        company = companies.get(j.ticker)
        if company is None:
            missing.append({"ticker": j.ticker, "name": j.name})
            continue
        if company.is_active:
            already.append({"ticker": j.ticker, "name": j.name})
            continue
        company.is_active = True
        added.append({"ticker": j.ticker, "name": j.name})

    if added:
        await EventLogger(db).record(
            source="screener",
            event_type="screener.watchlist_added",
            entity_type="screener_run",
            entity_id=str(run.id),
            summary=f"选股结果加入自选 {len(added)} 只："
            + "、".join(a["ticker"] for a in added[:20]),
            payload={"tickers": [a["ticker"] for a in added]},
        )
    await db.flush()
    return {
        "run_id": str(run.id),
        "added": added,
        "already": already,
        "missing": missing,
    }
