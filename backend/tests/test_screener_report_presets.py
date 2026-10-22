"""报告预设标注单测 — union/intersection 模式加"命中预设"列与分组说明；v1 报告不变。"""

from __future__ import annotations

from screener.report import build_report

RUN_V1 = {
    "id": "b1a2c3d4e5f6",
    "candidate_count": 1,
    "result_count": 1,
    "criteria_text": "ROE > 15",
}

RUN_PRESETS = {
    "id": "c2b3d4e5f6a7",
    "candidate_count": 2,
    "result_count": 1,
    "criteria_text": "预设组合（union）：核心资产 + 质量价值 GARP",
}

J = {
    "ticker": "600519",
    "name": "贵州茅台",
    "recommend": True,
    "reasons": ["ROE 高"],
    "criteria_hits": [{"criterion": "盈利具有持续性", "hit": True, "evidence": "ROE 30.2"}],
    "confidence": 0.9,
    "snapshot": {"price": 1500.0, "market_cap": 1.88e12},
    "status": "ok",
}

J_UNION = {
    **J,
    "snapshot": {**J["snapshot"], "hits": 2, "presets": ["核心资产", "质量价值 GARP"]},
}


def test_v1_report_unchanged():
    """mode=None（v1）报告：无预设列、无预设标注。"""
    report = build_report(RUN_V1, [J], RUN_V1["criteria_text"], [])
    assert "| 代码 | 名称 | 现价 | 总市值 | 置信度 |" in report
    assert "命中预设" not in report
    assert "命中：" not in report


def test_union_report_annotates_presets():
    """union 模式：推荐表加"命中预设"列，候选注明命中组合。"""
    report = build_report(RUN_PRESETS, [J_UNION], RUN_PRESETS["criteria_text"], [])
    assert "| 代码 | 名称 | 现价 | 总市值 | 置信度 | 命中预设 |" in report
    assert "核心资产 + 质量价值 GARP" in report


def test_union_report_single_preset():
    """命中单个预设也正常标注。"""
    j = {**J, "snapshot": {**J["snapshot"], "hits": 1, "presets": ["核心资产"]}}
    report = build_report(RUN_PRESETS, [j], RUN_PRESETS["criteria_text"], [])
    assert "核心资产" in report
