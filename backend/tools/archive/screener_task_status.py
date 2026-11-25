"""查 screener_run 任务队列状态。"""
import psycopg2

from _db import connect

conn = connect()
cur = conn.cursor()
cur.execute(
    """
    SELECT status, task_key, attempts, left(coalesce(error, ''), 70), created_at
    FROM core.task_records
    WHERE task_type = 'screener_run'
    ORDER BY created_at DESC
    LIMIT 5
    """
)
for row in cur.fetchall():
    print(row)
conn.close()
