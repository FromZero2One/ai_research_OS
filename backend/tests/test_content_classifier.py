"""content_classifier 纯函数单测（不依赖数据库）。"""

from __future__ import annotations

from document.content_classifier import classify_chunk


class TestClassifyChunk:
    def test_mda(self):
        text = "第三节 管理层讨论与分析。本年度公司经营情况讨论如下：主营业务收入稳步增长。"
        assert classify_chunk(text) == "mda"

    def test_risk(self):
        text = "公司可能面临的风险因素包括原材料价格波动和汇率风险。"
        assert classify_chunk(text) == "risk"

    def test_notes(self):
        text = "财务报表附注：本公司执行的会计政策包括收入确认与金融工具计量。"
        assert classify_chunk(text) == "notes"

    def test_announcement(self):
        text = "关于召开2025年第一次临时股东大会决议公告"
        assert classify_chunk(text) == "announcement"

    def test_other_default(self):
        assert classify_chunk("今日股价收盘价为 12.34 元，成交量放大。") == "other"
        assert classify_chunk("") == "other"
        assert classify_chunk("   ") == "other"

    def test_tie_prefers_mda(self):
        # mda 与 risk 各命中 1 个关键词 → 按优先顺序取 mda
        text = "管理层讨论与分析中提及公司风险管理措施。"
        assert classify_chunk(text) == "mda"

    def test_higher_score_wins(self):
        text = "重大风险提示：可能面临的风险包括行业下行。另外财务报表附注略。"
        assert classify_chunk(text) == "risk"
