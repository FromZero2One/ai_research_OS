"""查看某次运行某只票的完整判定（含证据引用），排查 insufficient 原因。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools/show_judgement.py <run_id> <ticker>
"""
import json
import sys

import psycopg2

from _db import connect

run_id, ticker = sys.argv[1], sys.argv[2]

conn = connect()
cur = conn.cursor()
cur.execute(
    """
    SELECT ticker, verdict, confidence, recommend, reasons, criteria_hits, snapshot, status
    FROM screener.screener_judgements
    WHERE run_id = %s AND ticker = %s
    """,
    (run_id, ticker),
)
row = cur.fetchone()
if not row:
    print("没有该判定")
    raise SystemExit(1)
print("ticker:", row[0], "verdict:", row[1], "confidence:", row[2], "recommend:", row[3])
print("reasons:", json.dumps(row[4], ensure_ascii=False, indent=2)[:1500])
print("criteria_hits:", json.dumps(row[5], ensure_ascii=False, indent=2)[:1200])
print("snapshot:", json.dumps(row[6], ensure_ascii=False, indent=2)[:1200])
print("status:", row[7])
conn.close()
