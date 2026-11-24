"""把已下载的年报 PDF 上传到文档中心并等待索引完成。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools\\upload_reports.py [--limit N]

读取 data/uploads/kb/manifest.csv；缺失的公司自动补进 company.companies
（is_active=false, priority=999），再以 multipart 上传并轮询索引状态。
"""

import argparse
import csv
import json
import time
import urllib.request
import uuid
from pathlib import Path

import httpx
import psycopg2

from _db import connect

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "uploads" / "kb"
BACKEND = "http://127.0.0.1:8000"


def ensure_company(cur, ticker: str, name: str) -> str:
    cur.execute("SELECT id FROM company.companies WHERE ticker=%s", (ticker,))
    row = cur.fetchone()
    if row:
        return str(row[0])
    new_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO company.companies (id, ticker, name, is_active, priority) "
        "VALUES (%s, %s, %s, false, 999)",
        (new_id, ticker, name),
    )
    print(f"  新增公司: {ticker} {name}", flush=True)
    return new_id


def upload(path: Path, title: str, company_id: str) -> dict:
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "application/pdf")}
        data = {"title": title, "doc_type": "annual_report", "company_id": company_id}
        resp = httpx.post(f"{BACKEND}/api/v1/documents/upload", files=files, data=data, timeout=300)
    resp.raise_for_status()
    return resp.json()


def wait_indexed(doc_id: str, timeout_s: int = 900) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = json.loads(
                urllib.request.urlopen(
                    f"{BACKEND}/api/v1/documents/{doc_id}/status", timeout=20
                ).read()
            )
        except Exception:
            time.sleep(10)
            continue
        if r.get("is_indexed"):
            return r
        time.sleep(10)
    return {"is_indexed": False, "timeout": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=[],
        help="仅上传这些代码（支持逗号分隔或空格分隔，建议加引号）",
    )
    args = parser.parse_args()

    with open(OUT_DIR / "manifest.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if args.tickers:
        wanted = {t.strip() for group in args.tickers for t in group.split(",") if t.strip()}
        rows = [r for r in rows if r["ticker"] in wanted]
    if args.limit:
        rows = rows[: args.limit]

    conn = connect()
    cur = conn.cursor()
    results = []
    for i, row in enumerate(rows, 1):
        path = Path(row["path"])
        if not path.exists():
            print(f"[{i}/{len(rows)}] {row['ticker']}: 文件缺失，跳过", flush=True)
            continue
        company_id = ensure_company(cur, row["ticker"], row["name"])
        conn.commit()
        title = f"{row['name']} {row['year']}年年度报告"
        cur.execute(
            "SELECT id, is_indexed FROM document.documents "
            "WHERE title=%s AND company_id=%s LIMIT 1",
            (title, company_id),
        )
        existing = cur.fetchone()
        if existing:
            print(
                f"[{i}/{len(rows)}] {row['ticker']}: 已存在（{existing[0]}），跳过上传", flush=True
            )
            results.append({"ticker": row["ticker"], "doc_id": str(existing[0]), "title": title})
            continue
        try:
            doc = upload(path, title, company_id)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(rows)}] {row['ticker']}: 上传失败 {str(e)[:120]}", flush=True)
            continue
        doc_id = doc.get("id") or doc.get("document_id")
        print(f"[{i}/{len(rows)}] {row['ticker']}: 已上传 {doc_id}", flush=True)
        results.append({"ticker": row["ticker"], "doc_id": doc_id, "title": title})

    conn.close()

    print("\n等待索引完成（解析/切片/Embedding）…", flush=True)
    for r in results:
        st = wait_indexed(r["doc_id"])
        print(
            f"  {r['ticker']}: is_indexed={st.get('is_indexed')} "
            f"chunks={st.get('chunk_count')} timeout={st.get('timeout', False)}",
            flush=True,
        )

    with open(OUT_DIR / "uploaded.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
