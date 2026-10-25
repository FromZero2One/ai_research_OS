"""诊断：回测票池来源（活跃公司 vs 外部全市场）。"""

import psycopg2

conn = psycopg2.connect(
    host="localhost", port=5432, dbname="airesearch", user="airesearch", password="airesearch_dev"
)
cur = conn.cursor()
cur.execute("SELECT count(*) FROM company.companies WHERE is_active = true")
print("活跃公司数:", cur.fetchone()[0])
cur.execute(
    "SELECT ticker, name FROM company.companies WHERE is_active = true ORDER BY ticker LIMIT 30"
)
print("活跃公司:", [r[0] for r in cur.fetchall()])
cur.execute("SELECT count(*) FROM company.companies")
print("公司总数:", cur.fetchone()[0])
conn.close()
