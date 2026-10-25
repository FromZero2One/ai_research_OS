"""查看某次选股运行的判定分布与推荐明细。"""
import json
import sys
import urllib.request
from collections import Counter

RUN = (
    sys.argv[1]
    if len(sys.argv) > 1
    else "dd7f9f64-c0e3-4c62-87bc-82ea279072e0"
)
ONLY = sys.argv[2] if len(sys.argv) > 2 else None
data = json.loads(urllib.request.urlopen(
    f"http://127.0.0.1:8000/api/v1/screener/runs/{RUN}", timeout=30).read())

judges = data.get("judgements") or []
if ONLY:
    for j in judges:
        if j.get("ticker") == ONLY:
            print(f"{ONLY}: verdict={j.get('verdict')} confidence={j.get('confidence')}")
            print("reasons:", str(j.get("reasons"))[:400])
    raise SystemExit
print(f"状态: {data['status']}  候选: {data['candidate_count']}  判定: {len(judges)}")
print("判定分布:", dict(Counter(j.get("verdict") for j in judges)))

print("\n推荐股:")
for j in judges:
    if j.get("recommend"):
        reasons = str(j.get("reasons") or "").replace("\n", " ")
        print(f"  {j.get('ticker')}  confidence={j.get('confidence')}  "
              f"理由={reasons[:120]}")

print("\n非推荐示例（前 5）:")
shown = 0
for j in judges:
    if j.get("recommend"):
        continue
    print(f"  {j.get('ticker')}  verdict={j.get('verdict')}  "
          f"理由={str(j.get('reasons') or '')[:100]}")
    shown += 1
    if shown >= 5:
        break
