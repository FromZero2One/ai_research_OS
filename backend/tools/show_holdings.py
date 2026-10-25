"""拉取指定回测最近一期的持仓明细（含名称）。"""
import json
import urllib.request

import psycopg2

RUNS = {
    "高成长": "1d4dd341-a562-441c-8ac2-d765af6c06e1",
    "金融价值": "142079ab-444c-4496-8c45-c8e4bcf07e7b",
}

conn = psycopg2.connect(host="localhost", port=5432, dbname="airesearch",
                        user="airesearch", password="airesearch_dev")
cur = conn.cursor()


def name_of(ticker: str) -> str:
    cur.execute("SELECT name FROM company.companies WHERE ticker=%s LIMIT 1", (ticker,))
    row = cur.fetchone()
    return row[0] if row else ""


for label, rid in RUNS.items():
    data = json.loads(urllib.request.urlopen(
        f"http://127.0.0.1:8000/api/v1/screener/backtests/{rid}", timeout=30).read())
    yearly = data["result"]["yearly"]
    last = yearly[-1]
    holdings = last.get("holdings") or []
    print(f"\n=== {label}（{last['rebalance_date']} 调仓）===")
    print(f"持仓 {len(holdings)} 只：")
    for h in holdings:
        if isinstance(h, dict):
            t = h.get("ticker", "")
            print(f"  {t} {h.get('name') or name_of(t)}")
        else:
            print(f"  {h} {name_of(str(h))}")
conn.close()
