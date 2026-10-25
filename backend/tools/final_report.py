"""最终报告：最近 6 次回测的成绩 + 逐期持仓 + 分段稳健性。"""

import json
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1/screener"


def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=30).read())


runs = get("/backtests?limit=12")["backtests"]
# 按 preset_id 去重，取最新一次 completed
latest = {}
for r in runs:
    if r["status"] == "completed" and r["preset_id"] not in latest:
        latest[r["preset_id"]] = r

for r in latest.values():
    d = get(f"/backtests/{r['id']}")
    res = d["result"]
    s = res["summary"]
    yearly = res["yearly"]
    print(f"\n=== {d.get('preset_name') or r['id'][:8]} ===")
    print(
        f"CAGR={s['cagr']:.2%} 基准={s['bench_cagr']:.2%} 超额={s['excess_cagr']:.2%} "
        f"Sharpe={s['sharpe']:.2f} Sortino={s['sortino']:.2f} "
        f"回撤={s['max_drawdown']:.2%} 胜率={s['win_rate']:.0%} Calmar={s['calmar']:.2f}"
    )
    sp = s.get("split_sample") or {}
    if sp.get("first_half") and sp.get("second_half"):
        f, sh = sp["first_half"], sp["second_half"]
        print(
            f"分段: 前半 CAGR={f['cagr']:.2%} 超额={f['excess_cagr']:.2%} | "
            f"后半 CAGR={sh['cagr']:.2%} 超额={sh['excess_cagr']:.2%} | "
            f"两段一致跑赢={sp.get('consistent_excess')}"
        )
    counts = [len(y.get("holdings") or []) for y in yearly]
    print(f"逐期持仓数: {counts} (空仓期={counts.count(0)})")
