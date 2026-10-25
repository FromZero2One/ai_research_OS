"""列出全部预设的量化规则与定性标准（排查标准可验证性用）。"""
import json

import psycopg2

DB = dict(host="localhost", port=5432, dbname="airesearch",
          user="airesearch", password="airesearch_dev")

conn = psycopg2.connect(**DB)
cur = conn.cursor()
cur.execute(
    """
    SELECT id, name, style_tag, is_active, qualitative, quant_rules, suggested_pool
    FROM screener.criteria_presets
    ORDER BY name
    """
)
for pid, name, style, active, qual, quant, pool in cur.fetchall():
    print("=" * 70)
    print(f"{name}  id={pid}  style={style}  active={active}  pool={pool}")
    print("量化规则:")
    for rule in quant or []:
        print("  -", json.dumps(rule, ensure_ascii=False))
    print("定性标准:")
    for q in qual or []:
        print("  *", q)
conn.close()
