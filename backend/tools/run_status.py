"""查最近选股运行状态（直连 PG，避免大响应 HTTP 超时）。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools/run_status.py [n]
"""
import sys

import psycopg2

from _db import connect

LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 3

conn = connect()
cur = conn.cursor()
cur.execute(
    """
    SELECT r.id, r.status, r.mode, r.candidate_count,
           (SELECT count(*) FROM screener.screener_judgements j WHERE j.run_id = r.id) AS judged,
           r.created_at, r.finished_at
    FROM screener.screener_runs r
    ORDER BY r.created_at DESC
    LIMIT %s
    """,
    (LIMIT,),
)
for run_id, status, mode, cand, judged, created, finished in cur.fetchall():
    print(f"{run_id}  status={status} mode={mode} 候选={cand} 判定={judged} "
          f"created={created:%H:%M:%S} finished={finished}")
conn.close()
