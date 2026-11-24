"""按预设排队跑实时选股，直到全部完成，每只推荐打印摘要。

用法（backend 目录，后端需运行）：
    .venv\\Scripts\\python -X utf8 tools\\run_presets_live.py [preset_id ...]
"""

import json
import sys
import time
import urllib.request

import psycopg2

from _db import connect

API = "http://127.0.0.1:8000/api/v1/screener"

DEFAULT = {
    "高成长": "70e6282d-da98-46c8-91db-20ec062b3d96",
    "深度价值": "9df4fd6f-b15e-4db2-a43c-048e09be1f36",
    "金融价值": "67fd20f8-86d0-458a-8782-252dd21454fc",
}


def post(path: str, body: dict) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def get(path: str, timeout: int = 120) -> dict:
    return json.loads(
        urllib.request.urlopen(API + path, timeout=timeout).read()
    )


def db_state(run_id: str) -> tuple[str, int, int]:
    """直连 PG 取状态（HTTP 大响应在深判时容易超时）。"""
    conn = connect()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status, candidate_count FROM screener.screener_runs WHERE id = %s",
            (run_id,),
        )
        row = cur.fetchone()
        cur.execute(
            "SELECT count(*) FROM screener.screener_judgements WHERE run_id = %s",
            (run_id,),
        )
        judged = cur.fetchone()[0]
    finally:
        conn.close()
    if row is None:
        return "missing", 0, 0
    return row[0], row[1] or 0, judged


def run_one(name: str, preset_id: str) -> None:
    print(f"\n{'=' * 60}\n预设: {name} ({preset_id})", flush=True)
    run = post("/runs", {"mode": "presets", "pool": "all", "preset_ids": [preset_id]})
    run_id = run["id"]
    print(f"run_id={run_id} 已启动", flush=True)

    started = time.time()
    last = None
    status = "pending"
    while True:
        time.sleep(20)
        status, total, done = db_state(run_id)
        msg = f"  [{int(time.time() - started)}s] status={status} 已判定 {done}/{total}"
        if msg != last:
            print(msg, flush=True)
            last = msg
        if status in ("completed", "failed", "missing"):
            break

    data = get(f"/runs/{run_id}", timeout=300) if status == "completed" else {}
    judges = data.get("judgements") or []
    counts: dict[str, int] = {}
    for j in judges:
        key = j.get("verdict") or "?"
        counts[key] = counts.get(key, 0) + 1
    print(f"状态={status} 候选={data.get('candidate_count')} 判定={len(judges)}")
    print("判定分布:", counts)
    print("推荐:")
    for j in judges:
        if j.get("recommend"):
            reasons = str(j.get("reasons") or "").replace("\n", " ")
            print(f"  {j.get('ticker')} conf={j.get('confidence')} {reasons[:140]}")


def main() -> None:
    args = sys.argv[1:]
    targets = (
        [(k, v) for k, v in DEFAULT.items() if v in args]
        if args
        else list(DEFAULT.items())
    )
    for name, pid in targets:
        run_one(name, pid)


if __name__ == "__main__":
    main()
