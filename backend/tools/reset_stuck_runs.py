"""把卡住的选股运行标记为 failed（后端崩溃后残留 pending/judging 状态会阻塞新运行）。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools/reset_stuck_runs.py            # 只看
    .venv\\Scripts\\python -X utf8 tools/reset_stuck_runs.py --apply    # 实际标记
"""
import sys

import psycopg2

from _db import connect

APPLY = "--apply" in sys.argv

conn = connect()
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
    # 同步把队列里的 screener_run 任务置 failed，否则后端重启会「恢复」并自动重跑
    cur.execute(
        """
        UPDATE core.task_records
        SET status = 'failed',
            completed_at = now(),
            error = COALESCE(error, 'reset: run aborted by operator')
        WHERE task_type = 'screener_run'
          AND status IN ('pending', 'running')
        """
    )
    print("已标记任务 failed:", cur.rowcount)
    conn.commit()
conn.close()
