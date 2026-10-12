"""Market services shared helpers — 避免跨 service 复制粘贴。

从 price/financial/profile/search 四个 service 中抽取的公共代码：
- AkshareMySQLAdapter 模块级单例（原为每 service 各持一份逐字重复的懒加载）
- DataFreshness 记录（原为 price/financial 两份逐字重复的延迟导入块）
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.akshare_mysql import AkshareMySQLAdapter

_shared_mysql: AkshareMySQLAdapter | None = None


def get_shared_mysql() -> AkshareMySQLAdapter:
    """共享 AkshareMySQLAdapter（无状态配置封装，单例即可）。"""
    global _shared_mysql
    if _shared_mysql is None:
        _shared_mysql = AkshareMySQLAdapter()
    return _shared_mysql


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
