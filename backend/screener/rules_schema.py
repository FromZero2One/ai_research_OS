"""结构化规则 schema — LLM 翻译标准的输出契约 + 手写校验（不引入 jsonschema 依赖）。

数字唯一事实源原则：metric 键对齐 market.financial_metrics 枚举指标 +
market.ratio_service 比率键 + 行情快照字段（price/turnover/market_cap）。
"""

from __future__ import annotations

from screener.valuation import QUALITY_METRICS, VALUATION_METRICS

# 行情快照字段（来自全市场快照，不依赖财务数据）
SNAPSHOT_METRICS: frozenset[str] = frozenset({"price", "turnover", "market_cap"})

# 财务指标：必须是 market.financial_metrics 中真实有市场级数据的指标。
# 口径 = yjbb（业绩报表）+ bs/cf（资产负债表/现金流）+ F10 主要指标。
FINANCIAL_METRICS: frozenset[str] = frozenset(
    {
        "revenue",
        "net_income",
        "eps",
        "total_assets",
        "total_liabilities",
        "operating_cash_flow",
        "roe",
        "gross_margin",
        "net_margin",
        "debt_to_equity",
        "asset_turnover",
        "inventory_turnover",
        "receivables_turnover",
        "current_ratio",
        "quick_ratio",
        "revenue_growth",
        "net_income_growth",
    }
)

# 曾有定义但当前没有任何市场级数据源的指标：翻译命中时明确报错，
# 引导 LLM/用户改写为定性标准，而不是产出「全员缺数据」的静默 0 候选。
UNAVAILABLE_METRICS: frozenset[str] = frozenset(
    {"gross_profit", "operating_profit", "rd_expense", "total_equity"}
)

# LLM 翻译可用的指标键（快照 + 财务 + 派生估值 + 盈利质量）
KNOWN_METRICS: frozenset[str] = (
    SNAPSHOT_METRICS | FINANCIAL_METRICS | VALUATION_METRICS | QUALITY_METRICS
)

# 以「元」为单位的指标：LLM 把「100亿」直译成 100 会让规则对全市场失效。
# 翻译阶段允许 LLM 输出 value + value_unit，由服务端换算，避免模型自己数零。
MONEY_METRICS = frozenset(
    {
        "market_cap",
        "revenue",
        "net_income",
        "operating_cash_flow",
        "total_assets",
        "total_liabilities",
    }
)
VALUE_UNITS = frozenset({"元", "万", "亿", "%", "倍"})

_ALLOWED_OPS = frozenset({">", ">=", "<", "<=", "=="})
_ALLOWED_POOLS = frozenset({"all", "main", "chinext", "star", "watchlist"})
_ALLOWED_POLICIES = frozenset({"exclude", "include"})

RULES_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "stock_pool": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["all", "main", "chinext", "star", "watchlist"]},
                "tickers": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["type"],
        },
        "quant_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": sorted(KNOWN_METRICS)},
                    "op": {"type": "string", "enum": sorted(_ALLOWED_OPS)},
                    "value": {"type": "number"},
                    "value_unit": {
                        "type": "string",
                        "enum": sorted(VALUE_UNITS),
                        "description": (
                            "金额类指标填 元/万/亿，百分比填 %，倍数填 倍；"
                            "服务端负责换算到基础单位"
                        ),
                    },
                    "missing_data_policy": {
                        "type": "string",
                        "enum": ["exclude", "include"],
                        "description": "数据缺失时 exclude=排除该公司，include=放行并计入命中",
                    },
                },
                "required": ["metric", "op", "value", "missing_data_policy"],
            },
        },
        "qualitative_criteria": {"type": "array", "items": {"type": "string"}},
        "candidate_limit": {"type": "integer", "minimum": 1, "maximum": 200},
    },
    "required": ["stock_pool", "quant_rules", "qualitative_criteria"],
}


def hash_criteria(text: str) -> str:
    """标准文档 hash（sha256 前 16 位）— 翻译缓存的失效键。"""
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def validate_rules(obj: object) -> list[str]:
    """校验规则 dict，返回错误列表（空列表 = 合法）。"""
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["rules 必须是对象"]

    pool = obj.get("stock_pool")
    if not isinstance(pool, dict):
        errors.append("stock_pool 缺失或不是对象")
    else:
        if pool.get("type") not in _ALLOWED_POOLS:
            errors.append(f"stock_pool.type 非法: {pool.get('type')!r}")
        tickers = pool.get("tickers", [])
        if not isinstance(tickers, list) or any(not isinstance(t, str) for t in tickers):
            errors.append("stock_pool.tickers 必须是字符串数组")

    quant = obj.get("quant_rules", [])
    if not isinstance(quant, list):
        errors.append("quant_rules 必须是数组")
    else:
        for i, rule in enumerate(quant):
            if not isinstance(rule, dict):
                errors.append(f"quant_rules[{i}] 不是对象")
                continue
            metric = rule.get("metric")
            if metric in UNAVAILABLE_METRICS:
                errors.append(
                    f"quant_rules[{i}].metric 暂无可用的市场级数据源: {metric!r}；"
                    "请改写为 qualitative_criteria 或改用其它指标"
                )
            elif metric not in KNOWN_METRICS:
                errors.append(f"quant_rules[{i}].metric 未知: {metric!r}")
            if rule.get("op") not in _ALLOWED_OPS:
                errors.append(f"quant_rules[{i}].op 非法: {rule.get('op')!r}")
            value = rule.get("value")
            unit = rule.get("value_unit")
            if unit is not None and unit not in VALUE_UNITS:
                errors.append(f"quant_rules[{i}].value_unit 非法: {unit!r}")
            if metric in MONEY_METRICS and unit in {"%", "倍"}:
                errors.append(f"quant_rules[{i}].value_unit 与金额指标不匹配: {unit!r}")
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                errors.append(f"quant_rules[{i}].value 必须是数字")
            elif (
                metric in MONEY_METRICS
                and unit is None
                and abs(float(value)) > 0
                and abs(float(value)) < 1e6
            ):
                errors.append(
                    f"quant_rules[{i}].value 疑似单位错误：{metric} 以元为单位"
                    "（1亿=100000000），请换算后再填，或提供 value_unit"
                )
            if rule.get("missing_data_policy") not in _ALLOWED_POLICIES:
                errors.append(f"quant_rules[{i}].missing_data_policy 非法")

    qual = obj.get("qualitative_criteria", [])
    if not isinstance(qual, list) or any(not isinstance(q, str) for q in qual):
        errors.append("qualitative_criteria 必须是字符串数组")

    # 无意义/含混标准的防线：翻译出零条件时明确报错，不静默产出空推荐
    quant_list = obj.get("quant_rules", [])
    if isinstance(quant_list, list) and isinstance(qual, list) and not quant_list and not qual:
        errors.append("标准文档未能翻译出任何有效筛选条件（量化与定性均为空）")

    limit = obj.get("candidate_limit", 50)
    if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 200):
        errors.append("candidate_limit 必须是 1-200 的整数")

    return errors
