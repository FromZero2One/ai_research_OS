"""把卡住的选股运行标记为 failed（后端崩溃后残留 pending/judging 状态会阻塞新运行）。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools/reset_stuck_runs.py            # 只看
    .venv\\Scripts\\python -X utf8 tools/reset_stuck_runs.py --apply    # 实际标记
"""
import sys

import psycopg2

DB = dict(host="localhost", port=5432, dbname="airesearch",
          user="airesearch", password="airesearch_dev")
APPLY = "--apply" in sys.argv

conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute(
    """
    SELECT id, status, candidate_count, created_at
    FROM screener.screener_runs
    WHERE status NOT IN ('completed', 'failed', 'cancelled')
    ORDER BY created_at DESC
    """
)
rows = cur.fetchall()
print("未结束的运行:", len(rows))
for run_id, status, cand, created in rows:
    print(f"  {run_id}  status={status} 候选={cand} created={created:%H:%M:%S}")

if APPLY and rows:
    cur.execute(
        """
        UPDATE screener.screener_runs
        SET status = 'failed',
            finished_at = now(),
            error = COALESCE(error, 'reset: backend crashed mid-run')
        WHERE status NOT IN ('completed', 'failed', 'cancelled')
        """
    )
    print("已标记 failed:", cur.rowcount)
    conn.commit()
conn.close()
