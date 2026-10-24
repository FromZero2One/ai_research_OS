"""Ingest A-share industry classification from Shenwan first-level indices.

Usage:
    ALL_PROXY= all_proxy= PYTHONPATH=. ./.venv/Scripts/python.exe -X utf8 \
        scripts/ingest_industry_sw.py [--dry-run]

One akshare child process loops the 31 first-level SW industries; each
industry's constituents come from `index_component_sw`. This covers the full
A-share market better than the Sina industry nodes (which missed many recent
bank/broker listings).
"""

from __future__ import annotations

import argparse
import json
import os
import uuid

import psycopg2
from psycopg2.extras import execute_batch

from market.akshare_executor import run_akshare
from screener.industry import parse_sw_industry_rows
from screener.ingest import _AKSHARE_PROLOGUE

_CHILD_CODE = _AKSHARE_PROLOGUE + r'''
import json, time
import akshare as ak
first = ak.sw_index_first_info()
out = []
for _, row in first.iterrows():
    code = str(row.get("行业代码") or "").replace(".SI", "").strip()
    name = str(row.get("行业名称") or "").strip()
    if not code or not name:
        continue
    try:
        cons = ak.index_component_sw(symbol=code)
    except Exception:
        continue
    for _, c in cons.iterrows():
        out.append({
            "ticker": str(c.get("证券代码") or "").strip(),
            "industry_code": code,
            "industry_name": name,
        })
    time.sleep(0.3)
print("__R__:" + json.dumps(out, ensure_ascii=False, default=str))
'''

DB = dict(
    host=os.getenv("PG_HOST", "localhost"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "airesearch"),
    user=os.getenv("PG_USER", "airesearch"),
    password=os.getenv("PG_PASSWORD", "airesearch_dev"),
)


def upsert_industries(rows: list[dict]) -> None:
    conn = psycopg2.connect(**DB)
    try:
        with conn.cursor() as cur:
            execute_batch(
                cur,
                """
                INSERT INTO market.stock_industry
                    (id, ticker, industry_code, industry_name, source, created_at, updated_at)
                VALUES (%s, %s, %s, %s, 'sw', now(), now())
                ON CONFLICT (ticker) DO UPDATE SET
                    industry_code = EXCLUDED.industry_code,
                    industry_name = EXCLUDED.industry_name,
                    source = EXCLUDED.source,
                    updated_at = now()
                """,
                [
                    (str(uuid.uuid4()), r["ticker"], r["industry_code"], r["industry_name"])
                    for r in rows
                ],
                page_size=500,
            )
        conn.commit()
    finally:
        conn.close()


def main(dry_run: bool = False) -> None:
    raw = run_akshare(_CHILD_CODE, timeout=600)
    if not raw or "__R__:" not in raw:
        raise SystemExit("申万行业拉取失败（akshare 子进程无有效输出）")

    payload = raw.split("__R__:", 1)[1].strip()
    rows = parse_sw_industry_rows(json.loads(payload))
    deduped: dict[str, dict] = {}
    for row in rows:
        deduped.setdefault(row["ticker"], row)

    industries = sorted({r["industry_name"] for r in deduped.values()})
    print(f"申万一级行业：{len(industries)} 个；覆盖股票：{len(deduped)} 只")
    print("行业列表：", "、".join(industries))
    if dry_run:
        print("dry-run：未写库")
        return

    upsert_industries(list(deduped.values()))
    print("已写入 market.stock_industry（source=sw）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
