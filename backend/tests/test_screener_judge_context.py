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


class TestIndustryContext:
    def test_includes_industry_and_financial_note(self):
        cand = {**CAND, "industry": "银行", "sector": "financial"}
        ctx = build_judge_context(cand, [])
        assert "行业: 银行" in ctx
        assert "金融行业" in ctx

    def test_unknown_industry(self):
        ctx = build_judge_context(CAND, [])
        assert "行业: 未知" in ctx


class TestContextFormatting:
    def test_money_metrics_have_units(self):
        """大额金额转成亿元，避免 LLM 对原始元值做单位换算（曾把 83.77 亿读成 837 亿）。"""
        ctx = build_judge_context(CAND, [], financials={"operating_cash_flow": 8377406414.45})
        assert "经营现金流=83.77亿元" in ctx
        assert "8377406414.45" not in ctx

    def test_percent_and_ratio_units(self):
        ctx = build_judge_context(CAND, [], financials={"roe": 21.89, "current_ratio": 4.01})
        assert "ROE=21.89%" in ctx
        assert "流动比率=4.01倍" in ctx

    def test_snapshot_market_cap_formatted(self):
        ctx = build_judge_context({**CAND, "market_cap": 205559656684.0}, [])
        assert "2055.60亿元" in ctx

    def test_extreme_margin_flagged_as_anomaly(self):
        """净利率 176% 这类越界值必须显式提示异常，不能被当作经营信号。"""
        ctx = build_judge_context(CAND, [], financials={"net_margin": 176.19})
        assert "数据异常提示" in ctx
        assert "176.19%" in ctx
