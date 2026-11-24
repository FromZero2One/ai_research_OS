"""诊断：PostgreSQL 活跃查询 / 锁等待。"""

import psycopg2

from _db import connect

conn = connect()
cur = conn.cursor()
cur.execute("""
    SELECT pid, state, wait_event_type, wait_event,
           now() - query_start AS duration, left(query, 100)
    FROM pg_stat_activity
    WHERE datname = 'airesearch' AND pid <> pg_backend_pid()
    ORDER BY query_start
""")
for r in cur.fetchall():
    print(f"pid={r[0]} state={r[1]} wait={r[2]}/{r[3]} dur={r[4]} q={r[5]}")
conn.close()
