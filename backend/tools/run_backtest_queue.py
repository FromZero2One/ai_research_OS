"""回测队列：依次为剩余预设排队（自动等待前一个完成，规避 409 并发限制）。

用法：后台运行。每 60s 轮询一次运行状态，完成后打印核心指标，再提交下一个。
"""

import json
import time
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1/screener"
# 当前正在跑的是「深度价值」，这里只排剩余 5 套
PRESETS = {
    "深度价值": "9df4fd6f-b15e-4db2-a43c-048e09be1f36",
    "核心资产": "b02a1716-41fd-4c41-8446-84af275fae23",
    "高成长": "70e6282d-da98-46c8-91db-20ec062b3d96",
    "GARP": "57119c75-d80e-4a6b-b6a6-49cde1411991",
    "周期反转": "40ef6bf8-c4da-4f35-acae-b7c2de4cd2b9",
    "金融价值": "67fd20f8-86d0-458a-8782-252dd21454fc",
}
YEARS = 3
POLL = 60


def get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=30).read())


def post(path, body):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def list_runs():
    data = get("/backtests?limit=50")
    return data.get("backtests", []) if isinstance(data, dict) else data


def wait_until_idle():
    while True:
        active = [r for r in list_runs() if r.get("status") in ("pending", "running")]
        if not active:
            return
        time.sleep(POLL)


def wait_run(run_id):
    while True:
        try:
            r = get(f"/backtests/{run_id}")
        except Exception as e:
            # 新建 run 可能存在短暂可见性竞态（404），重试而非崩溃
            print(f"  查询 {run_id[:8]} 失败(重试): {e}", flush=True)
            time.sleep(15)
            continue
        if r.get("status") in ("completed", "failed"):
            return r
        time.sleep(POLL)


def summary_of(r):
    res = r.get("result") or {}
    if isinstance(res, str):
        try:
            res = json.loads(res)
        except Exception:
            res = {}
    return res.get("summary") or r.get("summary") or {}


for name, pid in PRESETS.items():
    while True:  # 409/网络错误时重试同一预设，不跳过
        wait_until_idle()
        try:
            created = post("/backtests", {"preset_id": pid, "years": YEARS})
            break
        except Exception as e:
            print(f"[{name}] 提交失败(60s 后重试): {e}", flush=True)
            time.sleep(60)
    print(f"[{name}] 已创建 {created.get('id')}", flush=True)
    r = wait_run(created["id"])
    s = summary_of(r)
    if r.get("status") == "completed":
        print(
            f"[{name}] 完成 | CAGR={s.get('cagr')} 基准CAGR={s.get('bench_cagr')} "
            f"超额={s.get('excess_cagr')} Sharpe={s.get('sharpe')} "
            f"Sortino={s.get('sortino')} 最大回撤={s.get('max_drawdown')}",
            flush=True,
        )
    else:
        print(f"[{name}] 失败: {r.get('error')}", flush=True)

print("=== 回测队列完成 ===", flush=True)
