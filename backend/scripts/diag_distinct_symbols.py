# -*- coding: utf-8 -*-
"""诊断：distinct symbol 查询耗时 + 表索引。"""
import time

import pymysql

conn = pymysql.connect(
    host="8.137.104.120", user="root", password="root1314pwd",
    database="akshare", port=3306, connect_timeout=10,
)
try:
    cur = conn.cursor()
    t0 = time.time()
    cur.execute("SHOW INDEX FROM stock_history_daily_info_entity")
    for r in cur.fetchall():
        print("index:", r[2], "col:", r[4])
    print(f"index query elapsed={time.time()-t0:.1f}s")

    t0 = time.time()
    cur.execute(
        "SELECT DISTINCT symbol FROM stock_history_daily_info_entity "
        "WHERE date BETWEEN %s AND %s AND adjust = 'qfq'",
        ("2021-10-23", "2026-10-23"),
    )
    rows = cur.fetchall()
    print(f"distinct rows={len(rows)} elapsed={time.time()-t0:.1f}s")
finally:
    conn.close()
