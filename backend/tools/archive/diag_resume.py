# -*- coding: utf-8 -*-
"""调试：resume 查询为何不命中。"""
import asyncio
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def main() -> None:
    from sqlalchemy import func, select

    from core.database import managed_session
    from market.models import StockPrice

    start = dt.date(2021, 1, 1)
    end = dt.date(2021, 1, 31)
    async with managed_session() as db:
        # 模拟测试预置
        db.add_all(
            StockPrice(ticker="600519", date=dt.date(2020, 6, 1) + dt.timedelta(days=i), open=1, close=1, high=1, low=1, volume=1)
            for i in range(210)
        )
        await db.commit()

        total = (await db.execute(select(func.count()).select_from(StockPrice).where(StockPrice.ticker == "600519"))).scalar()
        in_window = (
            await db.execute(
                select(func.count()).select_from(StockPrice)
                .where(StockPrice.ticker == "600519", StockPrice.date >= start, StockPrice.date <= end)
            )
        ).scalar()
        done = (
            await db.execute(
                select(StockPrice.ticker)
                .where(StockPrice.date >= start, StockPrice.date <= end)
                .group_by(StockPrice.ticker)
                .having(func.count() >= 200)
            )
        ).scalars().all()
        print(f"total={total} in_window={in_window} done={done}")
        # 清理
        from sqlalchemy import delete

        await db.execute(delete(StockPrice).where(StockPrice.ticker == "600519"))
        await db.commit()


asyncio.run(main())
