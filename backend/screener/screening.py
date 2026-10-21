"""确定性初筛 — 全市场快照采集 + 量化规则求值 + 排名截断（纯函数可单测）。

LLM 只负责"理解标准"和"定性深判"，本模块全部确定性执行。
"""

from __future__ import annotations

import json

from core.exceptions import DataSourceError
from core.logging import logger
from market.akshare_executor import run_akshare
from market.domain import FinancialMetricEntry

# 全市场 A 股实时快照（东方财富）；ticker 经 env 传入为空 — 全市场查询无需参数
_SPOT_CODE = (
    "import json, sys\nimport akshare as ak\n"
    "try:\n"
    "    df = ak.stock_zh_a_spot_em()\n"
    "    if df is None or df.empty:\n"
    '        print("__R__:[]")\n'
    "    else:\n"
    '        cols = {"代码": "ticker", "名称": "name", "最新价": "price",\n'
    '                "换手率": "turnover", "总市值": "market_cap"}\n'
    '        out = df[list(cols)].rename(columns=cols).to_dict(orient="records")\n'
    '        print("__R__:" + json.dumps(out, ensure_ascii=False))\n'
    "except Exception as e:\n"
    '    print("E:" + str(e))\n'
)

_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
}

# 快照字段（可直接求值）；其余 metric 从财务指标取
_SNAPSHOT_FIELDS = frozenset({"price", "turnover", "market_cap"})


async def fetch_market_spot() -> list[dict]:
    """全市场 A 股快照（akshare 子进程）。失败 raise DataSourceError。"""
    raw = run_akshare(_SPOT_CODE)
    if raw is None:
        raise DataSourceError("akshare", "全市场快照采集失败（子进程无输出）")
    if raw.startswith("E:"):
        raise DataSourceError("akshare", f"全市场快照采集失败: {raw[2:]}")
    payload = raw.removeprefix("__R__:").strip()
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError as e:
        raise DataSourceError("akshare", f"快照 JSON 解析失败: {e}") from e
    # 数值字段清洗（akshare 可能返回 NaN/'-'）
    out: list[dict] = []
    for row in rows:
        clean: dict = {"ticker": str(row.get("ticker", "")).strip()}
        for field in ("name", "price", "turnover", "market_cap"):
            v = row.get(field)
            clean[field] = v
        out.append(clean)
    logger.info("全市场快照: %d 只", len(out))
    return out


def _metric_value(entries: list[FinancialMetricEntry], metric: str) -> float | None:
    """取该指标最新一期的值（按 fiscal_year, fiscal_period 降序）。"""
    _PERIOD_RANK = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "Annual": 4, "Semi": 2}
    best = max(
        (e for e in entries if e.metric_name == metric and e.metric_value is not None),
        key=lambda e: (e.fiscal_year, _PERIOD_RANK.get(e.fiscal_period, 0)),
        default=None,
    )
    return best.metric_value if best else None


def _rule_hit(rule: dict, candidate: dict, fin_entries: list[FinancialMetricEntry]) -> bool | None:
    """单条规则求值：True=命中，False=不命中，None=数据缺失。"""
    metric = rule["metric"]
    if metric in _SNAPSHOT_FIELDS:
        value = candidate.get(metric)
    else:
        value = _metric_value(fin_entries, metric)
    if value is None:
        return None
    return _OPS[rule["op"]](float(value), float(rule["value"]))


def evaluate_quant_rules(
    candidates: list[dict],
    rules: list[dict],
    financials_by_ticker: dict[str, list[FinancialMetricEntry]],
) -> tuple[list[dict], list[dict]]:
    """量化规则求值。

    返回 (通过者, 因缺数据被排除者)：
    - 规则命中 False → 淘汰（不进也不出两个列表，直接丢弃）
    - 数据缺失：missing_data_policy=exclude → excluded 列表；include → 放行并计入命中
    通过者附 score 字段（命中数/适用规则数）。
    """
    passed: list[dict] = []
    excluded: list[dict] = []
    for cand in candidates:
        fin_entries = financials_by_ticker.get(cand["ticker"], [])
        hits = 0
        dropped = False
        missing = False
        for rule in rules:
            result = _rule_hit(rule, cand, fin_entries)
            if result is None:
                if rule.get("missing_data_policy", "exclude") == "include":
                    hits += 1  # 缺数据放行并计入命中
                else:
                    missing = True
                continue
            if result:
                hits += 1
            else:
                dropped = True
                break
        if dropped:
            continue
        if missing and not hits and not _all_hit(cand, rules, fin_entries):
            # 存在 exclude 策略的规则缺数据且无法全部命中 → 因缺数据排除
            excluded.append(cand)
            continue
        passed.append({**cand, "score": score_candidate(hits, len(rules))})
    return passed, excluded


def _all_hit(cand: dict, rules: list[dict], fin_entries: list[FinancialMetricEntry]) -> bool:
    return all(_rule_hit(r, cand, fin_entries) is True for r in rules)


def score_candidate(hit: int, applicable: int) -> float:
    """初筛得分 = 命中条件数 / 适用条件数；无规则时 0.0。"""
    if applicable <= 0:
        return 0.0
    return hit / applicable


def rank_candidates(passed: list[dict], limit: int = 50) -> list[dict]:
    """按 score 降序、同分按 market_cap 降序，截断到 limit。"""
    ranked = sorted(passed, key=lambda c: (c.get("score", 0.0), c.get("market_cap") or 0.0), reverse=True)
    return ranked[:limit]
