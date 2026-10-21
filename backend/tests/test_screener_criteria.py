"""criteria 读写 + 规则 schema 校验单测（纯函数，不依赖数据库）。"""

from __future__ import annotations

import pytest

from screener import criteria as criteria_mod
from screener.rules_schema import RULES_JSON_SCHEMA, hash_criteria, validate_rules


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


def test_validate_bad_pool_type():
    rules = _valid_rules()
    rules["stock_pool"]["type"] = "all_us"
    assert validate_rules(rules) != []


def test_schema_is_dict():
    """RULES_JSON_SCHEMA 是合法 JSON Schema 结构（给 LLM 用）。"""
    assert RULES_JSON_SCHEMA["type"] == "object"
    assert "stock_pool" in RULES_JSON_SCHEMA["properties"]
