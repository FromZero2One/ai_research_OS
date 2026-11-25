"""检查回测所需 9 个报告期的指标完整性。"""

import psycopg2

from _db import connect

REQUIRED = ("eps", "total_assets", "operating_cash_flow")
PERIODS = [
    (2023, "Q3"),
    (2023, "Q4"),
    (2024, "Q2"),
    (2024, "Q3"),
    (2024, "Q4"),
    (2025, "Q2"),
    (2025, "Q3"),
    (2025, "Q4"),
    (2026, "Q2"),
]

c = connect()
cur = c.cursor()
for y, p in PERIODS:
    cur.execute(
        "SELECT metric_name FROM market.financial_metrics "
        "WHERE fiscal_year=%s AND fiscal_period=%s GROUP BY 1",
        (y, p),
    )
    names = {r[0] for r in cur.fetchall()}
    missing = [m for m in REQUIRED if m not in names]
    cur.execute(
        "SELECT count(*) FROM market.financial_metrics WHERE fiscal_year=%s AND fiscal_period=%s",
        (y, p),
    )
    total = cur.fetchone()[0]
    print(f"{y}{p}: 指标种数={len(names)} 行数={total} 缺失={missing or '无'}")
c.close()
