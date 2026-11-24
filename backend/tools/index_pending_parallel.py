"""并行索引所有未完成文档（绕过单线程任务队列，4 并发）。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools/index_pending_parallel.py
"""

import asyncio
import uuid

import psycopg2

# 独立进程需要显式导入所有模型，否则 SQLAlchemy 无法解析跨 schema 外键
import company.models  # noqa: F401
import document.models  # noqa: F401
import market.models  # noqa: F401
import screener.models  # noqa: F401
from core.container import create_container
from core.database import managed_session

DB = dict(host="localhost", port=5432, dbname="airesearch",
          user="airesearch", password="airesearch_dev")
CONCURRENCY = 6


def pending() -> list[tuple[str, str]]:
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    # 清掉单线程队列里的待办，避免重复索引
    cur.execute(
        "DELETE FROM core.task_records "
        "WHERE task_type='document_index' AND status='pending'"
    )
    deleted = cur.rowcount
    conn.commit()
    cur.execute(
        "SELECT id, title FROM document.documents WHERE NOT is_indexed ORDER BY created_at"
    )
    rows = [(str(r[0]), r[1]) for r in cur.fetchall()]
    conn.close()
    print(f"已清理待办任务 {deleted} 个；待索引 {len(rows)} 份")
    return rows


async def index_one(doc_id: str, title: str, sem: asyncio.Semaphore) -> None:
    async with sem:
        try:
            async with managed_session() as session:
                svc = create_container(session).document_service
                await svc.index_document(uuid.UUID(doc_id))
                await session.commit()
            print(f"OK   {title}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"FAIL {title}: {str(e)[:180]}", flush=True)


async def main() -> None:
    rows = pending()
    if not rows:
        print("没有待索引文档")
        return
    sem = asyncio.Semaphore(CONCURRENCY)
    await asyncio.gather(*(index_one(d, t, sem) for d, t in rows))


asyncio.run(main())
