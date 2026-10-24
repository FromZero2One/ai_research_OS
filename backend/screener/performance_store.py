"""推荐后表现快照 — 同一运行按自然日幂等保存。"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from screener.models import ScreenerPerformanceSnapshot


def snapshot_json(row: ScreenerPerformanceSnapshot) -> dict:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "as_of": row.as_of.isoformat(),
        "summary": row.summary,
        "meta": row.meta,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def save_snapshot(
    db: AsyncSession,
    run_id: uuid.UUID,
    payload: dict,
    as_of: date | None = None,
) -> ScreenerPerformanceSnapshot:
    """按 (run_id, as_of) upsert；payload 为 build_run_performance 的返回值。"""
    as_of = as_of or date.today()
    row = (
        await db.execute(
            select(ScreenerPerformanceSnapshot).where(
                ScreenerPerformanceSnapshot.run_id == run_id,
                ScreenerPerformanceSnapshot.as_of == as_of,
            )
        )
    ).scalar_one_or_none()
    summary = payload.get("summary") or {}
    stocks = payload.get("stocks") or []
    meta = {
        "message": payload.get("message"),
        "recommended_count": payload.get("recommended_count", 0),
        "with_entry_price": payload.get("with_entry_price", 0),
        "status": payload.get("status"),
    }
    if row is None:
        row = ScreenerPerformanceSnapshot(
            run_id=run_id, as_of=as_of, summary=summary, stocks=stocks, meta=meta
        )
        db.add(row)
    else:
        row.summary = summary
        row.stocks = stocks
        row.meta = meta
    await db.flush()
    return row


async def list_snapshots(
    db: AsyncSession, run_id: uuid.UUID
) -> list[ScreenerPerformanceSnapshot]:
    return list(
        (
            await db.execute(
                select(ScreenerPerformanceSnapshot)
                .where(ScreenerPerformanceSnapshot.run_id == run_id)
                .order_by(ScreenerPerformanceSnapshot.as_of.asc())
            )
        ).scalars().all()
    )
