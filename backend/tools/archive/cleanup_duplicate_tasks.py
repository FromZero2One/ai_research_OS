"""删除重复的 document_index 待办任务（已有其他活跃任务的 reindex 任务）。"""
import psycopg2

from _db import connect

c = connect()
cur = c.cursor()

cur.execute("""
    SELECT t.id, t.task_key, t.status, t.payload->>'document_id'
    FROM core.task_records t
    WHERE t.task_type='document_index'
      AND t.task_key LIKE 'reindex:%'
      AND t.status IN ('pending','running')
      AND EXISTS (
        SELECT 1 FROM core.task_records u
        WHERE u.task_type='document_index'
          AND u.status IN ('pending','running')
          AND u.payload->>'document_id' = t.payload->>'document_id'
          AND u.id <> t.id
          AND u.task_key NOT LIKE 'reindex:%'
      )
""")
dups = cur.fetchall()
print("重复 reindex 任务:", len(dups))
for d in dups:
    print(" ", d[1], d[2])

cur.execute("""
    DELETE FROM core.task_records t
    WHERE t.task_type='document_index'
      AND t.task_key LIKE 'reindex:%'
      AND t.status='pending'
      AND EXISTS (
        SELECT 1 FROM core.task_records u
        WHERE u.task_type='document_index'
          AND u.status IN ('pending','running')
          AND u.payload->>'document_id' = t.payload->>'document_id'
          AND u.id <> t.id
          AND u.task_key NOT LIKE 'reindex:%'
      )
""")
print("已删除 pending 重复任务:", cur.rowcount)
c.commit()

cur.execute(
    "SELECT task_key, status FROM core.task_records "
    "WHERE task_type='document_index' AND status IN ('pending','running') "
    "ORDER BY created_at"
)
print("剩余活跃索引任务:")
for r in cur.fetchall():
    print(" ", r[0], r[1])
c.close()
