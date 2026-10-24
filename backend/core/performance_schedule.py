"""推荐后表现定期快照 — 每个交易日收盘后记录最近运行的收益状态。

配置：PERFORMANCE_SNAPSHOT_SCHEDULE（默认工作日 17:10）。
同一运行同一天重复执行只会覆盖当日快照（幂等）。
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from core.database import managed_session
from core.logging import logger


async def scheduled_performance_snapshot(days: int = 30, limit: int = 30) -> dict:
    from screener.models import ScreenerRun
    from screener.performance_service import build_run_performance
    from screener.performance_store import save_snapshot

    cutoff = datetime.now(UTC) - timedelta(days=days)
    results: list[dict] = []
    async with managed_session() as db:
        runs = (
            await db.execute(
                select(ScreenerRun)
                .where(
                    ScreenerRun.status == "completed",
                    ScreenerRun.created_at >= cutoff,
                )
                .order_by(ScreenerRun.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        for run in runs:
            try:
                payload = await build_run_performance(db, run.id)
                row = await save_snapshot(db, run.id, payload)
                await db.commit()
                results.append(
                    {
                        "run_id": str(run.id),
                        "as_of": row.as_of.isoformat(),
                        "with_entry_price": payload.get("with_entry_price", 0),
                    }
                )
            except Exception as e:  # noqa: BLE001 — 单轮失败不阻断其余
                await db.rollback()
                logger.warning("表现快照失败 %s: %s", run.id, e)
                results.append({"run_id": str(run.id), "error": str(e)[:200]})
    return {"runs": len(results), "snapshots": results}


async def _handle_performance_snapshot(payload: dict) -> dict:
    return await scheduled_performance_snapshot(
        days=int(payload.get("days", 30)), limit=int(payload.get("limit", 30))
    )


from core.task_manager import register_handler  # noqa: E402

register_handler("screener_performance_snapshot", _handle_performance_snapshot)
