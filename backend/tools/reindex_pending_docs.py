"""为未索引文档重新排队 document_index 任务。"""
import asyncio

import psycopg2

from _db import connect

from core.database import managed_session
from core.task_manager import create_task



def pending() -> list[tuple[str, str]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT id, title FROM document.documents WHERE NOT is_indexed")
    rows = [(str(r[0]), r[1]) for r in cur.fetchall()]
    conn.close()
    return rows


async def main() -> None:
    rows = pending()
    if not rows:
        print("没有待索引文档")
        return
    async with managed_session() as db:
        for doc_id, title in rows:
            await create_task(
                "document_index", f"reindex:{doc_id}", {"document_id": doc_id}, db=db
            )
            print("已排队:", title, doc_id)
        await db.commit()


asyncio.run(main())
