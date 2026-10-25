"""查指定文档的任务状态。"""
import sys

import psycopg2

DOC = sys.argv[1] if len(sys.argv) > 1 else "ad3e6d1a-97e5-4271-8148-a06813950299"
c = psycopg2.connect(host="localhost", port=5432, dbname="airesearch",
                     user="airesearch", password="airesearch_dev")
cur = c.cursor()
cur.execute(
    "SELECT task_key, status, attempts, left(coalesce(error::text,''), 80), created_at "
    "FROM core.task_records WHERE task_type='document_index' "
    "AND payload->>'document_id'=%s ORDER BY created_at DESC LIMIT 5",
    (DOC,),
)
for r in cur.fetchall():
    print(r)
c.close()
