"""把美股（非纯数字 ticker）移出活跃列表，并汇报本地股票状态。"""
import psycopg2

c = psycopg2.connect(host="localhost", port=5432, dbname="airesearch",
                     user="airesearch", password="airesearch_dev")
cur = c.cursor()

cur.execute("SELECT ticker FROM company.companies WHERE is_active = true ORDER BY ticker")
print("停用前活跃:", [r[0] for r in cur.fetchall()])

cur.execute("UPDATE company.companies SET is_active=false WHERE ticker !~ '^[0-9]'")
c.commit()

cur.execute("SELECT count(*) FROM company.companies WHERE is_active = true")
print("停用后活跃数:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM company.companies WHERE is_active = true AND ticker ~ '^[0-9]'")
print("其中 A 股:", cur.fetchone()[0])
cur.execute("SELECT count(*) FROM company.companies")
print("公司总数:", cur.fetchone()[0])
cur.execute("SELECT count(DISTINCT ticker) FROM market.stock_prices")
print("本地有行情的票:", cur.fetchone()[0])
c.close()
