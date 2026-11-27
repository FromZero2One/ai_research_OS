"""把卡住的选股运行标记为 failed（后端崩溃后残留 pending/judging 状态会阻塞新运行）。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools/reset_stuck_runs.py            # 只看
    .venv\\Scripts\\python -X utf8 tools/reset_stuck_runs.py --apply    # 实际标记
"""
import sys

from _db import connect

APPLY = "--apply" in sys.argv

conn = connect()
cur = conn.cursor()
cur.execute(
    """
    SELECT id, status, candidate_count, created_at
    FROM screener.screener_runs
    WHERE status NOT IN ('completed', 'failed')
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
        WHERE status NOT IN ('completed', 'failed')
        """
    )
    print("已标记 failed:", cur.rowcount)
    # 注：任务队列（core.task_records）已随七次简化退役，后台为协程直跑，
    # 无需再复位任务行——重启后不会有「恢复并自动重跑」。
    conn.commit()
conn.close()
