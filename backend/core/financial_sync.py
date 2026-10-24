"""Scheduled job: refresh market-wide financial metrics for the latest report period.

三类数据源（业绩报表 / F10 主要指标 / 资产负债表+现金流）互相隔离：
单个数据源失败只记录状态，不阻断其余两类的更新。结果供调度接口查看。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import managed_session
from core.logging import logger

_LOADERS: tuple[tuple[str, str], ...] = (
    ("yjbb", "ingest_marketwide_yjbb"),
    ("main_finance", "ingest_marketwide_main_finance"),
    ("bs_cf", "ingest_marketwide_bs_cf"),
)


async def _run(db: AsyncSession) -> dict:
    from screener import ingest

    report_date = ingest._latest_report_date()
    families: dict[str, dict] = {}

    for name, attr in _LOADERS:
        loader = getattr(ingest, attr)
        try:
            # SAVEPOINT 隔离：单类补采失败不污染其它数据源
            async with db.begin_nested():
                count = await loader(db, report_date)
            await db.commit()
            families[name] = {"status": "ok", "count": count}
            logger.info(
                "财务数据更新 %s 完成：%d 条（报告期 %s）", name, count, report_date
            )
        except Exception as e:  # noqa: BLE001 — 数据源故障不应中断调度
            logger.warning("财务数据更新 %s 失败: %s", name, e)
            families[name] = {"status": "failed", "error": str(e)[:300]}

    return {"report_date": report_date, "families": families}


async def financial_data_update(db: AsyncSession | None = None) -> dict:
    """刷新最新报告期的全市场财务指标；db 为空时自管 session（调度入口）。"""
    if db is not None:
        return await _run(db)
    async with managed_session() as session:
        return await _run(session)
