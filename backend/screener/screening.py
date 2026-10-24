"""确定性初筛 — 全市场快照采集 + 量化规则求值 + 排名截断（纯函数可单测）。

LLM 只负责"理解标准"和"定性深判"，本模块全部确定性执行。
"""

from __future__ import annotations

import asyncio
import json

from core.exceptions import DataSourceError
from core.logging import logger
from market.akshare_executor import run_akshare
from market.domain import FinancialMetricEntry
from screener.valuation import (
    QUALITY_METRICS,
    VALUATION_METRICS,
    derive_quality,
    derive_valuation,
)

# 全市场 A 股实时快照。
# 注1：不走 akshare.stock_zh_a_spot_em（东财 push2 2026-10-22 起风控掐无 UA 请求 +
# 分页限流，59 页必挂）；改用新浪 Market_Center 分页接口（hs_a，含价格/换手率/
# 总市值），每页独立重试 + 节流，实测稳定。
# 注2：新浪 mktcap 单位为万元 → ×1e4 换算为元（与东财 f20 对齐）。
_SPOT_CODE = (
    "import os, time, json\n"
    "os.environ['NO_PROXY'] = '*'\n"
    "for _k in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):\n"
    "    os.environ.pop(_k, None)\n"
    "import requests\n"
    "_s = requests.Session()\n"
    "_s.trust_env = False\n"
    "_s.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'\n"
    "_s.headers['Referer'] = 'https://finance.sina.com.cn'\n"
    "_URL = 'https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData'\n"
    "try:\n"
    "    rows = []\n"
    "    page = 1\n"
    "    while True:\n"
    "        data = None\n"
    "        for attempt in range(5):\n"
    "            try:\n"
    "                r = _s.get(_URL, params={'page': page, 'num': 80, 'sort': 'symbol',\n"
    "                                         'asc': 1, 'node': 'hs_a'}, timeout=15)\n"
    "                data = r.json()\n"
    "                if data is not None:\n"
    "                    break\n"
    "            except Exception:\n"
    "                pass\n"
    "            time.sleep(2 * (attempt + 1))\n"
    "        if data is None:\n"
    "            raise RuntimeError(f'page {page} failed after 5 attempts')\n"
    "        if not data:\n"
    "            break\n"
    "        for it in data:\n"
    "            mktcap = it.get('mktcap')\n"
    "            rows.append({'ticker': it.get('code'), 'name': it.get('name'),\n"
    "                         'price': it.get('trade'),\n"
    "                         'turnover': it.get('turnoverratio'),\n"
    "                         'market_cap': (float(mktcap) * 1e4) if mktcap not in (None, '') else None})\n"
    "        page += 1\n"
    "        time.sleep(0.3)\n"
    "    if not rows:\n"
    "        raise RuntimeError('empty market snapshot')\n"
    '    print("__R__:" + json.dumps(rows, ensure_ascii=False))\n'
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


async def fetch_market_spot(force_refresh: bool = False) -> list[dict]:
    """全市场 A 股快照（带交易日缓存）。

    同一交易日第二次调用直接复用缓存（新浪分页 ~60 页节流需 20-30s），
    force_refresh=True 跳过读缓存仍回写。缓存故障/损坏静默降级为直接拉取。
    """
    cache = _get_cache()
    key = _spot_cache_key()
    if not force_refresh:
        try:
            raw = await cache.get(key)
            if raw:
                rows = json.loads(raw)
                if isinstance(rows, list) and rows:
                    logger.info("全市场快照命中缓存: %d 只", len(rows))
                    return rows
        except Exception as e:  # noqa: BLE001 — 缓存故障不阻塞拉取
            logger.warning("快照缓存读取失败，回源: %s", e)

    out = await _fetch_market_spot_raw()

    try:
        await cache.set(key, json.dumps(out, ensure_ascii=False), ttl=_SPOT_CACHE_TTL)
    except Exception as e:  # noqa: BLE001 — 缓存故障不阻塞返回
        logger.warning("快照缓存写入失败: %s", e)
    return out


# 快照缓存 TTL：24h（跨交易日后 key 里的日期变化，天然取新数据）
_SPOT_CACHE_TTL = 24 * 3600
_SPOT_CACHE_PREFIX = "screener:spot"


def _spot_cache_key() -> str:
    """按交易日分 key：当天收盘数据当天内复用，次日自动失效。"""
    from datetime import date

    return f"{_SPOT_CACHE_PREFIX}:{date.today().isoformat()}"


def _get_cache():
    """Redis 缓存（懒加载，失败由调用方兜底）。"""
    from core.adapters.cache import create_cache

    return create_cache()


async def _fetch_market_spot_raw() -> list[dict]:
    """真实拉取：akshare 子进程 + 解析清洗（无缓存逻辑，纯函数化便于测试）。"""
    raw = await asyncio.to_thread(run_akshare, _SPOT_CODE, None, 560)
    if raw is None:
        raise DataSourceError("akshare", "全市场快照采集失败（子进程无输出）")
    if raw.startswith("E:"):
        raise DataSourceError("akshare", f"全市场快照采集失败: {raw[2:]}")
    payload = raw.removeprefix("__R__:").strip()
    try:
        rows = json.loads(payload)
    except json.JSONDecodeError as e:
        raise DataSourceError("akshare", f"快照 JSON 解析失败: {e}") from e
    # 数值字段清洗（akshare 对停牌股返回 '-'/NaN → None，流入缺数据路径）
    import math

    from market.akshare_executor import to_float

    def _num(v) -> float | None:
        f = to_float(v)
        return None if f is None or math.isnan(f) else f

    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "ticker": str(row.get("ticker", "")).strip(),
                "name": row.get("name"),
                "price": _num(row.get("price")),
                "turnover": _num(row.get("turnover")),
                "market_cap": _num(row.get("market_cap")),
            }
        )
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
    """单条规则求值：True=命中，False=不命中，None=数据缺失。

    估值指标（pe/pb/ps）由快照市值 + 最新财务数据即时派生，不落库。
    """
    metric = rule["metric"]
    if metric in _SNAPSHOT_FIELDS:
        value = candidate.get(metric)
    elif metric in VALUATION_METRICS:
        value = derive_valuation(candidate, fin_entries).get(metric)
    elif metric in QUALITY_METRICS:
        value = derive_quality(fin_entries).get(metric)
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
    - 规则命中 False → 淘汰（直接丢弃，不进两个列表）
    - 数据缺失且 missing_data_policy=exclude → excluded（附 missing 指标列表，即使命中了其他规则）
    - 数据缺失且 missing_data_policy=include → 放行并计入命中
    通过者附 score 字段（命中数/适用规则数）。
    """
    passed: list[dict] = []
    excluded: list[dict] = []
    for cand in candidates:
        fin_entries = financials_by_ticker.get(cand["ticker"], [])
        hits = 0
        dropped = False
        missing_metrics: list[str] = []
        for rule in rules:
            result = _rule_hit(rule, cand, fin_entries)
            if result is None:
                if rule.get("missing_data_policy", "exclude") == "include":
                    hits += 1  # 缺数据放行并计入命中
                else:
                    missing_metrics.append(rule["metric"])
                continue
            if result:
                hits += 1
            else:
                dropped = True
                break
        if dropped:
            continue
        if missing_metrics:
            # exclude 策略的规则缺数据 → 排除（报告会列出缺失指标）
            excluded.append({**cand, "missing": missing_metrics})
            continue
        passed.append({**cand, "score": score_candidate(hits, len(rules))})
    return passed, excluded


def score_candidate(hit: int, applicable: int) -> float:
    """初筛得分 = 命中条件数 / 适用条件数；无规则时 0.0。"""
    if applicable <= 0:
        return 0.0
    return hit / applicable


def rank_candidates(passed: list[dict], limit: int = 50) -> list[dict]:
    """按 score 降序、同分按 market_cap 降序，截断到 limit。"""
    ranked = sorted(passed, key=lambda c: (c.get("score", 0.0), c.get("market_cap") or 0.0), reverse=True)
    return ranked[:limit]
