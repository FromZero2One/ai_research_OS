# -*- coding: utf-8 -*-
"""端到端真实冒烟：对「深度价值」预设跑 5 年真实回测。

前置：
- Docker 容器 airesearch-postgres 运行中
- .env 配置 BACKTEST_MYSQL_URL（外部 MySQL 前复权日线）
- 开发库已 alembic upgrade head

运行：cd backend; python scripts/demo_backtest_run.py
（首次运行会拉 5 年全市场日线 + 多期财务，可能需要 10-30 分钟）
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from core.database import managed_session  # noqa: E402
from screener.backtest_service import run_backtest  # noqa: E402
from screener.models import CriteriaPreset, ScreenerBacktestRun  # noqa: E402


async def main() -> None:
    async with managed_session() as db:
        preset = (
            await db.execute(
                select(CriteriaPreset).where(CriteriaPreset.name.like("%深度价值%")).limit(1)
            )
        ).scalar_one_or_none()
        if preset is None:
            presets = (await db.execute(select(CriteriaPreset))).scalars().all()
            names = [p.name for p in presets]
            raise SystemExit(f"未找到「深度价值」预设，现有：{names}")

        run = ScreenerBacktestRun(preset_id=preset.id, years=5, status="pending")
        db.add(run)
        await db.flush()
        run_id = run.id
        await db.commit()

        done = await run_backtest(db, run_id)
        await db.commit()

        print(f"status={done.status}")
        if done.error:
            print(f"error={done.error}")
        if done.result:
            import json

            print(json.dumps(done.result["summary"], ensure_ascii=False, indent=2, default=str))
        if done.report_path:
            print(f"report={done.report_path}")


if __name__ == "__main__":
    asyncio.run(main())
