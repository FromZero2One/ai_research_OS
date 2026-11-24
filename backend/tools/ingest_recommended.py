"""补采历史推荐票（主板采集范围外：002/300/301/688/001 前缀）。

从 screener.screener_judgements 取全部 verdict='recommend' 的去重 ticker，
跳过已有 >=200 行的，逐只调用后端 ingest，进度记录到独立 CSV。
"""

import os
import time
import urllib.request

import psycopg2

from _db import connect

BACKEND_URL = os.getenv("SCREENER_BACKEND_URL", "http://localhost:8000")
PROGRESS_FILE = os.getenv(
    "INGEST_PROGRESS_FILE", "E:/ai_research_OS/ingest_progress_recommended.csv"
)
BATCH_SIZE = 10
SLEEP_BETWEEN = 3
MIN_ROWS = 200
MAIN_BOARD = ("600", "601", "603", "605", "000")  # 正在由分片进程覆盖，跳过



def main():
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT DISTINCT ticker FROM screener.screener_judgements "
        "WHERE verdict='recommend' OR recommend = true"
    )
    tickers = sorted(r[0] for r in cur.fetchall())
    conn.close()

    targets = [t for t in tickers if not t.startswith(MAIN_BOARD)]
    print(f"历史推荐票（去重）{len(tickers)} 只，范围外 {len(targets)} 只待检查")

    done = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, encoding="utf-8-sig") as f:
            for line in f:
                parts = line.strip().split(",")
                if parts and (len(parts) < 3 or parts[2] != "fail"):
                    done.add(parts[0])
        print(f"已恢复进度：{len(done)} 只")

    ok = fail = skip = 0
    for i, ticker in enumerate(targets, 1):
        if ticker in done:
            skip += 1
            continue
        # 后端 ingest 是幂等 upsert，直接调用即可（已有完整数据的会 0 新增）
        try:
            req = urllib.request.Request(
                f"{BACKEND_URL}/api/v1/market/prices/{ticker}/ingest",
                method="POST",
                data=b"",
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=120)
            body = resp.read().decode()
            print(f"[{i}/{len(targets)}] {ticker}: HTTP {resp.status} {body[:80]}")
            ok += 1
            with open(PROGRESS_FILE, "a", encoding="utf-8-sig") as f:
                f.write(f"{ticker},,ok,{resp.status}\n")
        except Exception as e:
            print(f"[{i}/{len(targets)}] {ticker}: 失败 {e}")
            fail += 1
            with open(PROGRESS_FILE, "a", encoding="utf-8-sig") as f:
                f.write(f"{ticker},,fail,{str(e)[:120]}\n")
        if i % BATCH_SIZE == 0:
            time.sleep(SLEEP_BETWEEN)

    print(f"\n=== 完成 === 成功 {ok}（含幂等 0 新增）, 失败 {fail}, 跳过 {skip}")


if __name__ == "__main__":
    main()
