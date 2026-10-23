# -*- coding: utf-8 -*-
"""回测数据层冒烟：真连外部 MySQL 拉茅台 2021-01~06 日线。"""
import asyncio
import datetime as dt
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings  # noqa: E402
from screener.backtest_data import fetch_daily_from_mysql  # noqa: E402

settings.BACKTEST_MYSQL_URL = "mysql+pymysql://root:root1314pwd@8.137.104.120:3306/akshare"


async def main() -> None:
    out = await fetch_daily_from_mysql(
        ["600519"], dt.date(2021, 1, 1), dt.date(2021, 6, 30)
    )
    bars = out["600519"]
    print(f"rows={len(bars)}")
    print(f"first={bars[0]}")
    print(f"last={bars[-1]}")


if __name__ == "__main__":
    asyncio.run(main())
