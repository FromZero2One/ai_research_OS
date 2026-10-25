"""从巨潮资讯网下载指定股票的最新年度报告 PDF。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools\\fetch_cninfo_reports.py [run_id]

默认取最近一次 completed 选股运行的全部候选股票；下载到 data/uploads/kb/，
并写 manifest.csv（ticker,name,year,title,date,url,path,size）。
"""

import csv
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

import httpx

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "uploads" / "kb"
API = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
MAPPING_URL = "http://www.cninfo.com.cn/new/data/szse_stock.json"
BACKEND = "http://127.0.0.1:8000"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Referer": "http://www.cninfo.com.cn/new/commonUrl?url=disclosure/list/notice",
    "X-Requested-With": "XMLHttpRequest",
}
SKIP_WORDS = ("摘要", "英文", "已取消", "更正", "公告")


def list_run_tickers(run_id: str | None) -> list[str]:
    if run_id:
        data = json.loads(
            urllib.request.urlopen(f"{BACKEND}/api/v1/screener/runs/{run_id}", timeout=30).read()
        )
    else:
        runs = json.loads(
            urllib.request.urlopen(f"{BACKEND}/api/v1/screener/runs?limit=20", timeout=30).read()
        )["runs"]
        run = next(r for r in runs if r["status"] == "completed" and r.get("result_count"))
        data = json.loads(
            urllib.request.urlopen(f"{BACKEND}/api/v1/screener/runs/{run['id']}", timeout=30).read()
        )
    tickers = sorted({j["ticker"] for j in data.get("judgements") or []})
    print(f"运行 {data['id'][:8]}：候选 {len(tickers)} 只", flush=True)
    return tickers


def pick_annual(anns: list[dict]) -> dict | None:
    """从公告列表挑最近一期主年报（排除摘要/英文/更正/公告）。"""
    best = None
    for a in anns:
        title = str(a.get("announcementTitle") or "")
        if "年度报告" not in title or any(w in title for w in SKIP_WORDS):
            continue
        ts = int(a.get("announcementTime") or 0)
        if best is None or ts > best[0]:
            best = (ts, a, title)
    if not best:
        return None
    ts, a, title = best
    year = re.search(r"(\d{4})年年度报告", title)
    return {
        "title": title,
        "year": year.group(1) if year else "",
        "date": time.strftime("%Y-%m-%d", time.localtime(ts / 1000)),
        "url": "https://static.cninfo.com.cn/" + str(a.get("adjunctUrl")),
        "secName": a.get("secName"),
    }


def download(url: str, path: Path) -> int:
    req = urllib.request.Request(url, headers={"User-Agent": HEADERS["User-Agent"]})
    with urllib.request.urlopen(req, timeout=120) as resp, open(path, "wb") as f:
        while chunk := resp.read(65536):
            f.write(chunk)
    return path.stat().st_size


def main() -> None:
    run_id = sys.argv[1] if len(sys.argv) > 1 else None
    tickers = list_run_tickers(run_id)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers=HEADERS, timeout=30, trust_env=False) as client:
        mapping = {
            s.get("code"): s for s in (client.get(MAPPING_URL).json().get("stockList") or [])
        }
        print(f"cninfo 映射: {len(mapping)} 只", flush=True)

        rows = []
        for i, code in enumerate(tickers, 1):
            meta = mapping.get(code)
            if not meta:
                print(f"[{i}/{len(tickers)}] {code}: 映射缺失，跳过", flush=True)
                continue
            form = {
                "pageNum": 1,
                "pageSize": 30,
                "column": "szse",
                "tabName": "fulltext",
                "plate": "",
                "stock": f"{code},{meta.get('orgId')}",
                "searchkey": "",
                "secid": "",
                "category": "category_ndbg_szsh",
                "trade": "",
                "seDate": "",
                "sortName": "",
                "sortType": "",
                "isHLtitle": "true",
            }
            try:
                anns = client.post(API, data=form).json().get("announcements") or []
            except Exception as e:  # noqa: BLE001
                print(f"[{i}/{len(tickers)}] {code}: 查询失败 {str(e)[:80]}", flush=True)
                continue
            picked = pick_annual(anns)
            if not picked:
                print(f"[{i}/{len(tickers)}] {code}: 无年报", flush=True)
                continue
            safe_name = str(meta.get("zwjc") or picked["secName"] or code).replace("/", "_")
            path = OUT_DIR / f"{code}_{picked['year']}_annual.pdf"
            if path.exists() and path.stat().st_size > 0:
                size = path.stat().st_size
                print(
                    f"[{i}/{len(tickers)}] {code} {safe_name}: 已存在，跳过下载 "
                    f"({size / 1e6:.1f} MB)",
                    flush=True,
                )
            else:
                try:
                    size = download(picked["url"], path)
                except Exception as e:  # noqa: BLE001
                    print(f"[{i}/{len(tickers)}] {code}: 下载失败 {str(e)[:80]}", flush=True)
                    continue
                print(
                    f"[{i}/{len(tickers)}] {code} {safe_name}: {picked['title']} "
                    f"({size / 1e6:.1f} MB)",
                    flush=True,
                )
                time.sleep(1)
            rows.append(
                {
                    "ticker": code,
                    "name": safe_name,
                    "year": picked["year"],
                    "title": picked["title"],
                    "date": picked["date"],
                    "url": picked["url"],
                    "path": str(path),
                    "size": size,
                }
            )

    manifest = OUT_DIR / "manifest.csv"
    with open(manifest, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["ticker"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n完成: {len(rows)} 份 → {OUT_DIR}\n清单: {manifest}")


if __name__ == "__main__":
    main()
