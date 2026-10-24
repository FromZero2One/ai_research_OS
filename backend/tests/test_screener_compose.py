"""预设组合规则纯函数单测 — flatten/intersection/union 语义 + union 初筛。"""

from __future__ import annotations

from types import SimpleNamespace

from screener.compose import compose_rules, evaluate_quant_rules_by_preset


def _preset(name, quant_rules, qualitative=None, suggested_pool="all", style_tag="core"):
    return SimpleNamespace(
        name=name, quant_rules=quant_rules, qualitative=qualitative or [],
        suggested_pool=suggested_pool, style_tag=style_tag,
    )


def _rule(metric, op, value, policy="exclude"):
    return {"metric": metric, "op": op, "value": value, "missing_data_policy": policy}


# ── compose_rules ─────────────────────────────────────────────────────


def test_flatten_concat_with_later_override():
    """flatten：quant_rules 拼接 AND；同 metric 冲突按传入顺序后者覆盖。"""
    p1 = _preset("P1", [_rule("roe", ">", 10), _rule("market_cap", ">", 1e9)])
    p2 = _preset("P2", [_rule("roe", ">", 20), _rule("debt_to_equity", "<", 40)])
    rules = compose_rules([p1, p2], pool="main", combine="flatten")

    assert rules["combine"] == "flatten"
    assert rules["preset_names"] == ["P1", "P2"]
    assert rules["stock_pool"] == {"type": "main"}
    metrics = [r["metric"] for r in rules["quant_rules"]]
    # roe 只出现一次，取后者（P2）的阈值
    assert metrics.count("roe") == 1
    roe_rule = next(r for r in rules["quant_rules"] if r["metric"] == "roe")
    assert roe_rule["value"] == 20
    assert metrics == ["roe", "market_cap", "debt_to_equity"]  # 后者覆盖但不追加到尾部


def test_intersection_concat_all():
    """intersection：quant_rules 全拼接（AND），combine 标记。"""
    p1 = _preset("P1", [_rule("roe", ">", 10)])
    p2 = _preset("P2", [_rule("roe", ">", 15), _rule("market_cap", ">", 1e9)])
    rules = compose_rules([p1, p2], pool="all", combine="intersection")

    assert rules["combine"] == "intersection"
    assert len(rules["quant_rules"]) == 3  # 不去重，全部 AND
    assert rules["qualitative_criteria"] == []


def test_union_qualitative_dedupe_preserve_order():
    """union：定性条目去重拼接、保持首次出现顺序，并带来源预设前缀。"""
    p1 = _preset("P1", [_rule("roe", ">", 10)], qualitative=["护城河", "现金充裕"])
    p2 = _preset("P2", [_rule("roe", ">", 15)], qualitative=["现金充裕", "周期底部"])
    rules = compose_rules([p1, p2], pool="all", combine="union")

    assert rules["combine"] == "union"
    assert rules["qualitative_criteria"] == ["[P1] 护城河", "[P1] 现金充裕", "[P2] 周期底部"]


def test_pool_param_overrides_suggested_pool():
    """pool 参数覆盖各预设的 suggested_pool。"""
    p1 = _preset("P1", [_rule("roe", ">", 10)], suggested_pool="chinext")
    rules = compose_rules([p1], pool="star", combine="union")
    assert rules["stock_pool"] == {"type": "star"}


# ── evaluate_quant_rules_by_preset ────────────────────────────────────


def test_union_eval_counts_hits_and_dedupes():
    """union 初筛：每预设独立跑，票数排名数据 = hits 计数 + 命中预设名单去重。"""
    p1 = _preset("P1", [_rule("market_cap", ">", 1e9)])
    p2 = _preset("P2", [_rule("market_cap", ">", 2e9)])
    candidates = [
        {"ticker": "AAA", "name": "甲", "market_cap": 3e9},
        {"ticker": "BBB", "name": "乙", "market_cap": 1.5e9},
        {"ticker": "CCC", "name": "丙", "market_cap": 0.5e9},
    ]
    result = evaluate_quant_rules_by_preset(candidates, [p1, p2], financials_by_ticker={})

    assert set(result) == {"AAA", "BBB"}  # CCC 全不命中 → 不出现
    assert result["AAA"]["hits"] == 2
    assert result["AAA"]["presets"] == ["P1", "P2"]
    assert result["AAA"]["score"] == 1.0
    assert result["BBB"]["hits"] == 1
    assert result["BBB"]["presets"] == ["P1"]


def test_union_eval_collects_excluded_missing_only_unmatched():
    """union 缺失名单：只收「没有任何预设命中、且因缺数据被排除」的票。"""
    p1 = _preset("P1", [_rule("roe", ">", 15)])
    p2 = _preset("P2", [_rule("market_cap", ">", 1e9)])
    candidates = [
        {"ticker": "AAA", "name": "甲", "market_cap": 3e9},
        {"ticker": "BBB", "name": "乙", "market_cap": 2e9},
        {"ticker": "CCC", "name": "丙", "market_cap": 0.5e9},
    ]
    excluded: list[dict] = []
    result = evaluate_quant_rules_by_preset(
        candidates, [p1, p2], financials_by_ticker={}, collect_excluded=excluded
    )

    assert set(result) == {"AAA", "BBB"}  # 命中了 P2
    assert excluded == [
        {"ticker": "CCC", "name": "丙", "missing": ["roe"], "presets": ["P1"]}
    ]


def test_sector_scope_from_presets():
    industrial = _preset("核心", [_rule("market_cap", ">", 1e9)], style_tag="core")
    financial = _preset("金融", [_rule("pb", "<", 1.5)], style_tag="financial")
    assert compose_rules([industrial], "all", "union")["sector_scope"] == "industrial"
    assert compose_rules([financial], "all", "union")["sector_scope"] == "financial"
    assert compose_rules([industrial, financial], "all", "union")["sector_scope"] == "all"


def test_sector_scope_bank_insurance():
    bank = _preset("银行", [_rule("pb", "<", 1.5)], style_tag="bank")
    insurance = _preset("保险", [_rule("pb", "<", 2)], style_tag="insurance")
    assert compose_rules([bank], "all", "union")["sector_scope"] == "bank"
    assert compose_rules([insurance], "all", "union")["sector_scope"] == "insurance"
    assert compose_rules([bank, insurance], "all", "union")["sector_scope"] == "financial"


def test_union_eval_bank_scope():
    bank = _preset("银行", [_rule("market_cap", ">", 1e9)], style_tag="bank")
    candidates = [
        {"ticker": "BANK", "industry": "银行", "sector": "financial", "market_cap": 1e10},
        {"ticker": "INS", "industry": "非银金融", "sector": "financial", "market_cap": 1e10},
        {"ticker": "IND", "industry": "电子", "sector": "industrial", "market_cap": 1e10},
    ]
    result = evaluate_quant_rules_by_preset(candidates, [bank], {})
    assert set(result) == {"BANK"}


def test_union_eval_sector_isolation():
    """金融预设只看金融股；工业预设排除金融股（unknown 保留）。"""
    industrial = _preset("工业", [_rule("market_cap", ">", 1e9)], style_tag="core")
    financial = _preset("金融", [_rule("market_cap", ">", 1e9)], style_tag="financial")
    candidates = [
        {"ticker": "BANK", "name": "银行", "sector": "financial", "market_cap": 1e10},
        {"ticker": "IND", "name": "工业", "sector": "industrial", "market_cap": 1e10},
        {"ticker": "UNK", "name": "未知", "sector": "unknown", "market_cap": 1e10},
    ]
    fin = evaluate_quant_rules_by_preset(candidates, [financial], {})
    ind = evaluate_quant_rules_by_preset(candidates, [industrial], {})
    assert set(fin) == {"BANK"}
    assert set(ind) == {"IND", "UNK"}


def test_union_eval_financial_metric_rules():
    """union 初筛：财务指标规则走 financials_by_ticker。"""
    from market.domain import FinancialMetricEntry

    p1 = _preset("P1", [_rule("roe", ">", 15)])
    candidates = [
        {"ticker": "AAA", "name": "甲", "market_cap": 3e9},
        {"ticker": "BBB", "name": "乙"},
    ]
    financials = {
        "AAA": [
            FinancialMetricEntry(
                metric_name="roe", metric_value=18.0,
                fiscal_year=2026, fiscal_period="Q2",
            )
        ],
        "BBB": [
            FinancialMetricEntry(
                metric_name="roe", metric_value=10.0,
                fiscal_year=2026, fiscal_period="Q2",
            )
        ],
    }
    result = evaluate_quant_rules_by_preset(candidates, [p1], financials_by_ticker=financials)
    assert set(result) == {"AAA"}
    assert result["AAA"]["hits"] == 1
