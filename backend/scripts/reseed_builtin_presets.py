"""幂等重灌内置预设/指标种子（seeds.py 改动后执行一次）。

用法：cd backend && .venv\\Scripts\\python scripts\\reseed_builtin_presets.py
"""

from __future__ import annotations

import asyncio

from core.config import settings
from core.database import engine
from screener.seeds import insert_builtin_seeds


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync_conn: insert_builtin_seeds(sync_conn))
    print("内置指标/预设种子已重灌。")


if __name__ == "__main__":
    assert settings, "配置加载失败"
    asyncio.run(main())
