# -*- coding: utf-8 -*-
"""跑一轮真实的 presets 模式选股（union），展示全流程效果。"""
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"

# 绕过系统代理（clash 对 localhost 断连）；东财风控要求浏览器 UA
import os

os.environ["NO_PROXY"] = "*"
_UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}


def get(path):
    req = urllib.request.Request(BASE + path, headers=_UA)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return json.load(opener.open(req, timeout=30))


def post(path, body=None):
    data = json.dumps(body).encode() if body is not None else b""
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json", **_UA}, method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        resp = opener.open(req, timeout=30)
        return resp.status, json.load(resp)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


print("=" * 60)
print("① 指标库")
m = get("/api/v1/screener/metrics")
print(f"   共 {len(m['metrics'])} 个指标")
for x in m["metrics"][:6]:
    print(f"   - {x['key']:<22} {x['name_cn']}")
print()

print("② 内置预设")
p = get("/api/v1/screener/presets")
for x in p["presets"]:
    tag = "内置" if x["is_builtin"] else "自建"
    print(f"   - {x['name']:<12} [{x['style_tag']}] {tag} "
          f"量化规则 {len(x['quant_rules'])} 条, 定性 {len(x['qualitative'])} 条")
print()

# 选「周期反转」（只依赖市值+负债率，确定性最强）+「深度价值」做 union
chosen = [x for x in p["presets"] if x["style_tag"] in ("cycle", "value")]
ids = [x["id"] for x in chosen]
print("③ 触发选股：union 组合", "+".join(x["name"] for x in chosen))
print("   预设条件：")
for x in chosen:
    rules = ", ".join(f"{r['metric']} {r['op']} {r['value']}" for r in x["quant_rules"])
    print(f"   - {x['name']}: {rules}")

status, run = post("/api/v1/screener/runs", {
    "mode": "presets", "pool": "all", "preset_ids": ids, "combine": "union",
})
print(f"\n   POST /runs → {status}")
if status == 409:
    print("   已有进行中的运行（可能是历史残留）:", run)
    sys.exit(0)
if status != 201:
    print("   触发失败:", run)
    sys.exit(1)

run_id = run["id"]
print(f"   run_id = {run_id[:8]}...  mode={run.get('mode')} combine={run.get('combine')}")
print()

# 轮询（真实全市场快照 + 财务补采 + LLM 深判，可能要几分钟）
print("④ 等待完成（真实 akshare 全市场快照 + bs/cf 补采 + LLM 深判）...")
last = None
deadline = time.time() + 25 * 60
while time.time() < deadline:
    time.sleep(10)
    d = get(f"/api/v1/screener/runs/{run_id}")
    if d["status"] != last:
        print(f"   [{time.strftime('%H:%M:%S')}] {d['status']}  候选={d.get('candidate_count')}")
        last = d["status"]
    if d["status"] in ("completed", "failed"):
        break

print()
print("=" * 60)
if d["status"] == "failed":
    print("运行失败:", d.get("error"))
    sys.exit(1)

print("⑤ 运行结果")
print(f"   候选 {d['candidate_count']} 只, 推荐 {d['result_count']} 只")
rules = d.get("rules") or {}
print(f"   组装规则: {len(rules.get('quant_rules', []))} 条量化 + {len(rules.get('qualitative_criteria', []))} 条定性")
print(f"   来源预设: {rules.get('preset_names')}")
print()

js = d.get("judgements") or []
rec = [j for j in js if j.get("recommend") is True]
print("⑥ 推荐列表（含命中预设标注）:")
for j in rec[:8]:
    snap = j.get("snapshot") or {}
    print(f"   {j['ticker']} {j['name']:<8} 置信度={j.get('confidence')} "
          f"命中预设={snap.get('presets')} (hits={snap.get('hits')})")

# 报告
print()
print("⑦ 报告片段:")
r = get(f"/api/v1/screener/runs/{run_id}/report")
lines = r["report"].splitlines()
for ln in lines[:6]:
    print("  ", ln)
# 找命中预设表格行
in_table = False
for ln in lines:
    if "| 代码 |" in ln:
        in_table = True
    if in_table:
        print("  ", ln)
        if ln.startswith("---") or (in_table and not ln.startswith("|")):
            break
        if len([l for l in lines[:lines.index(ln)+1] if l.startswith("|")]) > 6:
            break
print()
print(f"报告路径: {d.get('report_path')}")
