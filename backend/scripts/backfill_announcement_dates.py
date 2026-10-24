"""Backfill `announcement_date` by re-ingesting yjbb for historical periods.

yjbb rows carry `最新公告日期`; the parser now persists it. Re-running the
market-wide yjbb ingest updates both values and announcement dates idempotently.

Usage:
    ALL_PROXY= all_proxy= PYTHONPATH=. ./.venv/Scripts/python.exe -X utf8 \
        scripts/backfill_announcement_dates.py
"""

from __future__ import annotations

import asyncio

from core.database import managed_session
from screener.ingest import ingest_marketwide_yjbb

DATES = ["20250331", "20250630", "20250930", "20251231", "20260630"]


async def main() -> None:
    async with managed_session() as db:
        for date in DATES:
            try:
                async with db.begin_nested():
                    count = await ingest_marketwide_yjbb(db, date)
                await db.commit()
                print(f"{date}: {count} 条", flush=True)
            except Exception as e:  # noqa: BLE001 — 单期失败继续
                print(f"{date} 失败: {e}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
