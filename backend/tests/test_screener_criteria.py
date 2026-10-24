"""criteria 读写 + 规则 schema 校验单测（纯函数，不依赖数据库）。"""

from __future__ import annotations

from screener import criteria as criteria_mod
from screener.rules_schema import (
    KNOWN_METRICS,
    RULES_JSON_SCHEMA,
    UNAVAILABLE_METRICS,
    hash_criteria,
    validate_rules,
)

# ── criteria IO ──────────────────────────────────────────────────────


def test_read_criteria_default_nonempty():
    """默认文档存在且含股票池声明。"""
    text = criteria_mod.read_criteria()
    assert len(text) > 0
    assert "股票池" in text


def test_write_read_roundtrip(tmp_path, monkeypatch):
    target = tmp_path / "criteria.md"
    monkeypatch.setattr(criteria_mod, "criteria_path", lambda: target)
    criteria_mod.write_criteria("# 我的标准\nROE > 15%")
    assert criteria_mod.read_criteria() == "# 我的标准\nROE > 15%"


def test_criteria_path_points_at_module_dir():
    p = criteria_mod.criteria_path()
    assert p.name == "criteria.md"
    assert p.parent.name == "screener"


# ── hash ─────────────────────────────────────────────────────────────


def test_hash_stable():
    assert hash_criteria("abc") == hash_criteria("abc")
    assert len(hash_criteria("abc")) == 16


def test_hash_changes_with_text():
    assert hash_criteria("abc") != hash_criteria("abd")


# ── validate_rules ───────────────────────────────────────────────────


def _valid_rules() -> dict:
    return {
        "stock_pool": {"type": "all", "tickers": []},
        "quant_rules": [
            {"metric": "roe", "op": ">", "value": 15.0, "missing_data_policy": "exclude"}
        ],
        "qualitative_criteria": ["行业格局清晰"],
        "candidate_limit": 50,
    }


def test_validate_ok():
    assert validate_rules(_valid_rules()) == []


def test_validate_missing_stock_pool():
    rules = _valid_rules()
    del rules["stock_pool"]
    assert validate_rules(rules) != []


def test_validate_bad_op():
    rules = _valid_rules()
    rules["quant_rules"][0]["op"] = "≈"
    assert validate_rules(rules) != []


def test_validate_unknown_metric():
    rules = _valid_rules()
    rules["quant_rules"][0]["metric"] = "magic_factor"
    assert validate_rules(rules) != []


def test_known_metrics_exclude_unavailable_ones():
    """白名单只能包含 market.financial_metrics 里真实有数据的指标。"""
    assert UNAVAILABLE_METRICS.isdisjoint(KNOWN_METRICS)
    assert {"gross_profit", "operating_profit", "rd_expense", "total_equity"} == UNAVAILABLE_METRICS
    assert {"roe", "market_cap", "operating_cash_flow"} <= KNOWN_METRICS
    assert {"pe", "pb", "ps"} <= KNOWN_METRICS
    assert {"cfo_to_ni", "cfo_to_revenue", "accrual_ratio"} <= KNOWN_METRICS
    assert {
        "roic", "interest_coverage", "cash_ratio", "fcff",
        "cfo_to_operating_profit", "tax_rate", "interest_debt_ratio",
        "peg", "fcf_yield",
        "net_interest_margin", "non_performing_loan", "gross_loans",
        "loan_provision_ratio", "first_adequacy_ratio", "npl_ratio",
        "net_roi", "earned_premium", "solvency_ar",
    } <= KNOWN_METRICS


def test_validate_money_unit_mistake_rejected():
    """『市值大于100亿』被直译成 market_cap > 100 → 单位错误，必须拦下。"""
    rules = _valid_rules()
    rules["quant_rules"][0] = {
        "metric": "market_cap", "op": ">", "value": 100, "missing_data_policy": "exclude"
    }
    errors = validate_rules(rules)
    assert any("单位" in e and "market_cap" in e for e in errors)


def test_validate_value_unit_accepted():
    rules = _valid_rules()
    rules["quant_rules"][0] = {
        "metric": "market_cap", "op": ">", "value": 100,
        "value_unit": "亿", "missing_data_policy": "exclude",
    }
    assert validate_rules(rules) == []


def test_validate_money_value_in_yuan_accepted():
    rules = _valid_rules()
    rules["quant_rules"][0] = {
        "metric": "market_cap", "op": ">", "value": 1e10, "missing_data_policy": "exclude"
    }
    assert validate_rules(rules) == []


def test_validate_unavailable_metric_has_actionable_message():
    """命中无数据源的指标要明确提示改写为定性标准，而不是笼统的"未知指标"。"""
    rules = _valid_rules()
    rules["quant_rules"][0]["metric"] = "rd_expense"
    errors = validate_rules(rules)
    assert any("数据源" in e and "qualitative_criteria" in e for e in errors)


def test_validate_bad_pool_type():
    rules = _valid_rules()
    rules["stock_pool"]["type"] = "all_us"
    assert validate_rules(rules) != []


def test_validate_empty_rules_rejected():
    """quant_rules 和 qualitative_criteria 全空 → 无效（防止无意义标准静默通过）。"""
    rules = {
        "stock_pool": {"type": "all", "tickers": []},
        "quant_rules": [],
        "qualitative_criteria": [],
        "candidate_limit": 50,
    }
    assert validate_rules(rules) != []


def test_schema_is_dict():
    """RULES_JSON_SCHEMA 是合法 JSON Schema 结构（给 LLM 用）。"""
    assert RULES_JSON_SCHEMA["type"] == "object"
    assert "stock_pool" in RULES_JSON_SCHEMA["properties"]
