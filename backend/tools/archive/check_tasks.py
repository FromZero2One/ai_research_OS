"""查看回测任务与任务队列状态。"""

import psycopg2

from _db import connect

conn = connect()
cur = conn.cursor()

cur.execute("""SELECT id, preset_id, status, error, created_at, finished_at
               FROM screener.backtest_runs ORDER BY created_at DESC LIMIT 5""")
print("=== backtest_runs ===")
for r in cur.fetchall():
    print(f"  {str(r[0])[:8]} status={r[2]} created={r[4]} err={str(r[3])[:80] if r[3] else '-'}")

cur.execute("""SELECT * FROM core.task_records ORDER BY created_at DESC LIMIT 8""")
print("=== task_records ===")
cols = [d[0] for d in cur.description]
print("  列:", cols)
for row in cur.fetchall():
    d = dict(zip(cols, row))
    print(
        f"  {str(d.get('id'))[:8]} type={d.get('task_type')} status={d.get('status')} "
        f"created={d.get('created_at')} err={str(d.get('error'))[:80] if d.get('error') else '-'}"
    )
conn.close()
