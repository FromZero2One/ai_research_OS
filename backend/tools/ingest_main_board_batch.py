"""
分批采集主板股票行情数据。
从 company.companies 读取 is_active=false 的主板股票，逐个调用采集接口。
支持中断恢复（已有 >=200 根 K 线的自动跳过）。

环境变量：
  SCREENER_BACKEND_URL  后端 API 地址（默认 http://localhost:8000）
  PG_HOST / PG_PORT / PG_DB / PG_USER / PG_PASSWORD  数据库连接（与后端一致）
  INGEST_PROGRESS_FILE  进度记录文件路径（默认 ./ingest_progress.csv）
"""
import os
import sys
import time
import csv
import uuid
import psycopg2
import urllib.request
import json
import argparse

BACKEND_URL = os.getenv("SCREENER_BACKEND_URL", "http://localhost:8000")
BATCH_SIZE = 10   # 每批10支，约4-6分钟，反馈快
SLEEP_BETWEEN = 3 # 秒，避免触发风控
MIN_ROWS = 200    # 视为完整的最小行数

DB = dict(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "airesearch"),
    user=os.getenv("PG_USER", "airesearch"),
    password=os.getenv("PG_PASSWORD", "airesearch_dev"),
)

PROGRESS_FILE = os.getenv("INGEST_PROGRESS_FILE", "./ingest_progress.csv")


def get_pending_tickers():
    """从 company.companies 获取待采集的主板股票（is_active=false）。"""
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT c.ticker, c.name
        FROM company.companies c
        LEFT JOIN market.stock_prices sp ON sp.ticker = c.ticker
        WHERE c.is_active = false AND c.priority = 999
        GROUP BY c.ticker, c.name
        HAVING COUNT(sp.ticker) = 0 OR COUNT(sp.ticker) < %s
        ORDER BY c.ticker
    """, (MIN_ROWS,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_existing_count(ticker):
    """查询某只股票已有多少行股价。"""
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM market.stock_prices WHERE ticker=%s", (ticker,))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt


def ingest_ticker(ticker):
    """调用后端采集接口。"""
    url = f"{BACKEND_URL}/api/v1/market/prices/{ticker}/ingest"
    req = urllib.request.Request(url, method='POST', data=b'', headers={'Content-Type': 'application/json'})
    try:
        resp = urllib.request.urlopen(req, timeout=120)
        body = resp.read().decode()
        return resp.status, body
    except Exception as e:
        return None, str(e)


def main(limit=None):
    pending = get_pending_tickers()
    if limit:
        pending = pending[:limit]
    total = len(pending)
    print(f"待采集股票共 {total} 只 (本次限制 {limit if limit else '全部'})")
    if total == 0:
        print("无待采集股票，退出。")
        return

    # 进度文件
    done = set()
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8-sig') as f:
            for line in f:
                parts = line.strip().split(',')
                if parts:
                    done.add(parts[0])
        print(f"已恢复进度：{len(done)} 只已完成")

    success = 0
    fail = 0
    skipped = 0

    for i, (ticker, name) in enumerate(pending, 1):
        if ticker in done:
            skipped += 1
            continue

        # 先检查已有行数（中断恢复时可能已部分采集）
        existing = get_existing_count(ticker)
        if existing >= MIN_ROWS:
            print(f"[{i}/{total}] {ticker} {name}: 已有 {existing} 行，跳过")
            skipped += 1
            with open(PROGRESS_FILE, 'a', encoding='utf-8-sig') as f:
                f.write(f"{ticker},{name},skipped,{existing}\n")
            done.add(ticker)
            continue

        status, body = ingest_ticker(ticker)
        if status == 201:
            try:
                data = json.loads(body)
                ingested = data.get('ingested', 0)
                print(f"[{i}/{total}] {ticker} {name}: 采集成功，新增 {ingested} 行")
                success += 1
            except Exception:
                print(f"[{i}/{total}] {ticker} {name}: 采集成功（状态 201）")
                success += 1
            with open(PROGRESS_FILE, 'a', encoding='utf-8-sig') as f:
                f.write(f"{ticker},{name},ok,{body}\n")
        else:
            print(f"[{i}/{total}] {ticker} {name}: 采集失败 HTTP={status} {body[:200]}")
            fail += 1
            with open(PROGRESS_FILE, 'a', encoding='utf-8-sig') as f:
                f.write(f"{ticker},{name},fail,{status},{body[:200]}\n")

        # 每批休息
        if i % BATCH_SIZE == 0:
            print(f"\n--- 已处理 {i} 只，休息 {SLEEP_BETWEEN} 秒避免风控 ---\n")
            time.sleep(SLEEP_BETWEEN)

    print(f"\n=== 完成 ===")
    print(f"成功: {success}, 失败: {fail}, 跳过: {skipped}, 总计: {total}")
    print(f"进度文件: {PROGRESS_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="本次最多采集数量")
    args = parser.parse_args()
    main(limit=args.limit)
