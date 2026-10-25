"""置信度分布（检查 LLM 自评是否退化成几档固定值）。"""
import sys

import psycopg2

DB = dict(host="localhost", port=5432, dbname="airesearch",
          user="airesearch", password="airesearch_dev")
RUN = sys.argv[1] if len(sys.argv) > 1 else "163a867c-b5df-4027-8c55-a4fd499f3934"

conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute(
    """
    SELECT confidence, verdict, count(*)
    FROM screener.screener_judgements
    WHERE run_id = %s
    GROUP BY 1, 2 ORDER BY 1 DESC NULLS LAST
    """,
    (RUN,),
)
print("confidence | verdict | count")
for row in cur.fetchall():
    print("  ", row)
conn.close()
