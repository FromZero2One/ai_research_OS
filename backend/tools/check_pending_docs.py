"""列出未完成索引的文档 + 对应任务状态。"""
import psycopg2

c = psycopg2.connect(host="localhost", port=5432, dbname="airesearch",
                     user="airesearch", password="airesearch_dev")
cur = c.cursor()
cur.execute("""
    SELECT d.id, d.title, d.chunk_count, d.is_indexed, d.file_size_bytes
    FROM document.documents d WHERE NOT d.is_indexed
""")
rows = cur.fetchall()
print("未索引文档:", len(rows))
for r in rows:
    print(" ", r[1], "size=", r[4])

cur.execute("""
    SELECT task_type, status, payload, left(coalesce(error::text,''), 120), created_at
    FROM core.task_records WHERE task_type='document_index'
    ORDER BY created_at DESC LIMIT 5
""")
print("\n最近 document_index 任务:")
for r in cur.fetchall():
    print(f"  status={r[1]} payload={str(r[2])[:60]} err={r[3]}")
c.close()
