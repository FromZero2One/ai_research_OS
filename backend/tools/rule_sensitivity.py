"""预设阈值敏感性扫描：逐条规则放宽/收紧，回测看超额变化。

做法：备份预设规则 → 逐个变体 UPDATE 规则 → POST 回测 → 轮询结果 → 恢复原规则。
仅用于离线分析，运行期间不要同时手动改预设。

用法（backend 目录）：
    .venv\\Scripts\\python -X utf8 tools\\rule_sensitivity.py
"""

import json
import os
import time
import urllib.request

import psycopg2

BASE = "http://127.0.0.1:8000/api/v1/screener"
YEARS = int(os.getenv("BACKTEST_YEARS", "5"))
POLL = 30

# 要扫描的预设（name → id）及变体：rule_metric → (放宽系数, )
TARGETS = {
    "GARP": {
        "id": "57119c75-d80e-4a6b-b6a6-49cde1411991",
        "variants": [("roic", 0.7), ("roe", 0.8), ("net_margin", 0.8), ("pe", 1.5)],
    },
    "核心资产": {
        "id": "b02a1716-41fd-4c41-8446-84af275fae23",
        "variants": [("roic", 0.7), ("roe", 0.8), ("market_cap", 0.33)],
    },
}

DB = dict(host="localhost", port=5432, dbname="airesearch",
          user="airesearch", password="airesearch_dev")


def api_get(path):
    return json.loads(urllib.request.urlopen(BASE + path, timeout=30).read())


def api_post(path, body):
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def list_runs():
    return api_get("/backtests?limit=50").get("backtests", [])


def wait_idle():
    while True:
        if not [r for r in list_runs() if r.get("status") in ("pending", "running")]:
            return
        time.sleep(POLL)


def wait_run(rid):
    while True:
        try:
            r = api_get(f"/backtests/{rid}")
        except Exception:
            time.sleep(15)
            continue
        if r.get("status") in ("completed", "failed"):
            return r
        time.sleep(POLL)


def run_variant(preset_id):
    wait_idle()
    created = api_post("/backtests", {"preset_id": preset_id, "years": YEARS})
    return wait_run(created["id"])


def main():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    for name, cfg in TARGETS.items():
        preset_id = cfg["id"]
        cur.execute("SELECT quant_rules FROM screener.criteria_presets WHERE id=%s", (preset_id,))
        original = cur.fetchone()[0]
        print(f"\n=== {name} 基准规则: {json.dumps(original, ensure_ascii=False)[:200]}...")
        try:
            for metric, factor in cfg["variants"]:
                rules = json.loads(json.dumps(original))
                changed = False
                for rule in rules:
                    if rule.get("metric") == metric:
                        old = rule.get("value")
                        rule["value"] = round(float(old) * factor, 4)
                        changed = True
                        print(
                            f"\n[{name}] 变体: {metric} {old} → {rule['value']} (×{factor})",
                            flush=True,
                        )
                if not changed:
                    continue
                cur.execute(
                    "UPDATE screener.criteria_presets SET quant_rules=%s WHERE id=%s",
                    (json.dumps(rules, ensure_ascii=False), preset_id))
                conn.commit()

                r = run_variant(preset_id)
                if r.get("status") == "completed":
                    res = r.get("result") or {}
                    if isinstance(res, str):
                        res = json.loads(res)
                    s = res.get("summary") or {}
                    print(f"[{name}] {metric}×{factor}: CAGR={s.get('cagr'):.2%} "
                          f"超额={s.get('excess_cagr'):.2%} Sharpe={s.get('sharpe'):.2f} "
                          f"回撤={s.get('max_drawdown'):.2%}", flush=True)
                else:
                    print(f"[{name}] {metric}×{factor}: 失败 {r.get('error')}", flush=True)
        finally:
            cur.execute(
                "UPDATE screener.criteria_presets SET quant_rules=%s WHERE id=%s",
                (json.dumps(original, ensure_ascii=False), preset_id))
            conn.commit()
            print(f"[{name}] 原规则已恢复", flush=True)
    conn.close()


if __name__ == "__main__":
    main()
