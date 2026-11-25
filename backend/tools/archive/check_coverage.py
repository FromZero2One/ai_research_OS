"""当前行情覆盖统计（临时检查脚本）。"""

import psycopg2

from _db import connect

conn = connect()
cur = conn.cursor()
cur.execute("SELECT count(*) FROM market.stock_prices")
print("行情总行数:", cur.fetchone()[0])
cur.execute(
    "SELECT count(*) FROM (SELECT ticker FROM market.stock_prices "
    "GROUP BY ticker HAVING count(*)>=200) t"
)
print("覆盖>=200根的票:", cur.fetchone()[0])
cur.execute("SELECT max(date) FROM market.stock_prices")
print("最新日期:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM company.companies WHERE is_active=false AND priority=999")
print("待采主板公司(companies):", cur.fetchone()[0])
conn.close()
