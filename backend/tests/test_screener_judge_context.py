"""深判上下文带初筛命中明细 — LLM 从"重新验证数字"变为"聚焦定性 + 复核异常"。"""

from __future__ import annotations

from screener.judge import build_judge_context

CAND = {
    "ticker": "600519",
    "name": "贵州茅台",
    "price": 1500.0,
    "turnover": 0.3,
    "market_cap": 1.88e12,
    "score": 0.9,
}


class TestPresetHitsInContext:
    def test_includes_preset_names_and_score(self):
        """union 模式候选带 hits/presets 字段 → 上下文展示命中的预设与得分。"""
        cand = {**CAND, "hits": 2, "presets": ["核心资产", "GARP"]}
        ctx = build_judge_context(cand, [])
        assert "核心资产" in ctx
        assert "GARP" in ctx
        assert "命中预设" in ctx

    def test_without_hits_has_no_preset_section(self):
        """freeform 候选无 hits/presets → 不出现预设区块（向后兼容）。"""
        ctx = build_judge_context(CAND, [])
        assert "命中预设" not in ctx

    def test_hits_without_names_graceful(self):
        """有 hits 无 presets 名单（异常数据）→ 不展示预设行，不崩溃。"""
        cand = {**CAND, "hits": 1, "presets": []}
        ctx = build_judge_context(cand, [])
        assert "600519" in ctx
