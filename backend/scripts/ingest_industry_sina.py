"""Ingest A-share industry classification from Sina into market.stock_industry.

Usage:
    ALL_PROXY= all_proxy= PYTHONPATH=. ./.venv/Scripts/python.exe -X utf8 \
        scripts/ingest_industry_sina.py [--limit-industries N] [--dry-run]

Sina endpoints (same source as the screener market snapshot):
  - newSinaHy.php                         → industry list (JS variable)
  - Market_Center.getHQNodeData?node=...  → constituents (JSON, paginated)
"""

from __future__ import annotations

import argparse
import os
import time
import uuid

import psycopg2
import requests
from psycopg2.extras import execute_batch

from screener.industry import INDUSTRY_SOURCE, parse_industry_constituents, parse_industry_list

LIST_URL = "https://vip.stock.finance.sina.com.cn/q/view/newSinaHy.php"
CONS_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
    "Market_Center.getHQNodeData"
)

DB = dict(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "airesearch"),
    user=os.getenv("PG_USER", "airesearch"),
    password=os.getenv("PG_PASSWORD", "airesearch_dev"),
)


def _session() -> requests.Session:
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(key, None)
    session = requests.Session()
    session.trust_env = False
    session.headers["User-Agent"] = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    )
    session.headers["Referer"] = "https://finance.sina.com.cn"
    return session


def _get(session: requests.Session, url: str, params: dict | None = None, retries: int = 5):
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = session.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp
        except Exception as e:  # noqa: BLE001 — retry transient Sina failures
            last_error = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"request failed after {retries} attempts: {last_error}")


def fetch_industries(session: requests.Session) -> list[dict]:
    resp = _get(session, LIST_URL)
    resp.encoding = "gbk"
    return parse_industry_list(resp.text)


def fetch_constituents(session: requests.Session, node: str) -> list[dict]:
    members: list[dict] = []
    page = 1
    while True:
        resp = _get(
            session,
            CONS_URL,
            params={"page": page, "num": 80, "sort": "symbol", "asc": 1, "node": node},
        )
        try:
            rows = resp.json()
        except ValueError:
            rows = []
        if not rows:
            break
        members.extend(rows)
        page += 1
        time.sleep(0.25)
    return parse_industry_constituents(members)


def upsert_industries(rows: list[tuple[str, str, str]]) -> None:
    """rows = [(ticker, industry_code, industry_name)]."""
    conn = psycopg2.connect(**DB)
    try:
        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO market.stock_industry
                    (id, ticker, industry_code, industry_name, source, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (ticker) DO UPDATE SET
                    industry_code = EXCLUDED.industry_code,
                    industry_name = EXCLUDED.industry_name,
                    source = EXCLUDED.source,
                    updated_at = now()
                """,
                [
                    (str(uuid.uuid4()), ticker, code, name, INDUSTRY_SOURCE)
                    for ticker, code, name in rows
                ],
                page_size=500,
            )
        conn.commit()
    finally:
        conn.close()


def main(limit_industries: int | None = None, dry_run: bool = False) -> None:
    session = _session()
    industries = fetch_industries(session)
    if limit_industries:
        industries = industries[:limit_industries]
    print(f"行业数：{len(industries)}")

    members: dict[str, tuple[str, str]] = {}
    failed: list[str] = []
    for index, industry in enumerate(industries, 1):
        code, name = industry["code"], industry["name"]
        try:
            rows = fetch_constituents(session, code)
        except Exception as e:  # noqa: BLE001 — one industry failure shouldn't stop the run
            print(f"[{index}/{len(industries)}] {name} 失败: {e}")
            failed.append(name)
            continue

        added = 0
        for row in rows:
            ticker = row["ticker"]
            if ticker not in members:
                members[ticker] = (code, name)
                added += 1
        print(f"[{index}/{len(industries)}] {name}: {len(rows)} 只（新增 {added}）")

    print(f"\n覆盖股票：{len(members)} 只；失败行业：{len(failed)} 个")
    if failed:
        print("失败行业:", ", ".join(failed))
    if dry_run:
        print("dry-run：未写库")
        return

    upsert_industries([(t, c, n) for t, (c, n) in members.items()])
    print("已写入 market.stock_industry")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit-industries", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(limit_industries=args.limit_industries, dry_run=args.dry_run)
