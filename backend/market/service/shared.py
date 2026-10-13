"""Market services shared helpers — 避免跨 service 复制粘贴。

DataFreshness 记录（原为 price/financial 两份逐字重复的延迟导入块）。
MySQL 镜像层已移除：A 股数据统一走 akshare subprocess 直连 + PG 缓存。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


async def record_freshness(
    session: AsyncSession,
    ticker: str,
    data_type: str,
    record_count: int | None = None,
    status: str = "ok",
) -> None:
    """记录一次成功采集的新鲜度（只应在真实采集路径调用，读缓存不要调）。"""
    from market.service.freshness_service import FreshnessService

    await FreshnessService(session).record_fetch(
        ticker, data_type, record_count=record_count, status=status
    )
