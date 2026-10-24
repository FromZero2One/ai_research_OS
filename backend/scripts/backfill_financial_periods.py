"""Backfill market-wide financials for periods required by TTM calculations.

TTM at 2026Q2 = FY2025 + 2026H1 - 2025H1, so we need 2025-06-30 and
2025-12-31 in addition to the already-ingested 2026-06-30.

Usage:
    ALL_PROXY= all_proxy= PYTHONPATH=. ./.venv/Scripts/python.exe -X utf8 \
        scripts/backfill_financial_periods.py [--dates 20250630,20251231]
"""

from __future__ import annotations

import argparse
import asyncio

from core.database import managed_session
from screener import ingest

_FAMILIES = (
    ("yjbb", ingest.ingest_marketwide_yjbb),
    ("bs_cf", ingest.ingest_marketwide_bs_cf),
)


async def run(dates: list[str]) -> None:
    async with managed_session() as db:
        for date in dates:
            for name, loader in _FAMILIES:
                try:
                    # SAVEPOINT 隔离单期/单类失败，避免污染其它回补
                    async with db.begin_nested():
                        count = await loader(db, date)
                    await db.commit()
                    print(f"{date} {name}: {count} 条", flush=True)
                except Exception as e:  # noqa: BLE001 — 单期失败继续下一期
                    print(f"{date} {name} 失败: {e}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dates",
        default="20250630,20251231",
        help="逗号分隔的报告期 YYYYMMDD",
    )
    args = parser.parse_args()
    asyncio.run(run([d.strip() for d in args.dates.split(",") if d.strip()]))
