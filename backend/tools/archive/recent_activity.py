"""看最近 5 分钟的选股/检索活动（判断深判是否还在推进）。"""
import psycopg2

from _db import connect

conn = connect()
cur = conn.cursor()

cur.execute("SELECT now()")
print("现在:", cur.fetchone()[0])

for schema, table in (("core", "event_log"), ("core", "task_records")):
    try:
        cur.execute(
            f"SELECT count(*), max(created_at) FROM {schema}.{table} "
            "WHERE created_at > now() - interval '5 minutes'"
        )
        print(f"{schema}.{table} 近5分钟:", cur.fetchone())
    except Exception as e:  # noqa: BLE001
        print(schema, table, "查询失败:", str(e)[:80])
        conn.rollback()

try:
    cur.execute(
        "SELECT event_type, count(*), max(created_at) FROM core.event_log "
        "WHERE created_at > now() - interval '10 minutes' "
        "GROUP BY event_type ORDER BY 2 DESC LIMIT 8"
    )
    print("\n近10分钟事件:")
    for row in cur.fetchall():
        print("  ", row)
except Exception as e:  # noqa: BLE001
    print("事件查询失败:", str(e)[:80])
conn.close()
