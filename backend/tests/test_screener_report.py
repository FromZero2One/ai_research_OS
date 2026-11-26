"""报告生成纯函数单测。"""

from __future__ import annotations

from screener.report import build_report, report_path_for

RUN = {
    "id": "b1a2c3d4e5f6",
    "candidate_count": 3,
    "result_count": 2,
    "criteria_text": "ROE > 15\n行业格局稳定",
}

JUDGEMENTS = [
    {
        "ticker": "600519",
        "name": "贵州茅台",
        "recommend": True,
        "reasons": ["ROE 高", "品牌壁垒"],
        "criteria_hits": [
            {"criterion": "ROE > 15", "hit": True, "evidence": "ROE 30.2"},
            {"criterion": "行业格局稳定", "hit": True, "evidence": "高端白酒双寡头"},
        ],
        "confidence": 0.9,
        "snapshot": {"price": 1500.0, "market_cap": 1.88e12},
        "status": "ok",
    },
    {
        "ticker": "300750",
        "name": "宁德时代",
        "recommend": False,
        "reasons": ["竞争加剧"],
        "criteria_hits": [{"criterion": "ROE > 15", "hit": False, "evidence": "ROE 12"}],
        "confidence": 0.6,
        "snapshot": {"price": 200.0, "market_cap": 8.8e11},
        "status": "ok",
    },
    {
        "ticker": "000001",
        "name": "平安银行",
        "recommend": None,
        "reasons": [],
        "criteria_hits": [],
        "confidence": None,
        "snapshot": {},
        "status": "failed",
        "error": "LLM 返回坏 JSON",
    },
]

EXCLUDED_MISSING = [{"ticker": "688981", "name": "中芯国际", "missing": ["roe"]}] * 1


class TestBuildReport:
    def test_recommended_table(self):
        report = build_report(RUN, JUDGEMENTS, RUN["criteria_text"], EXCLUDED_MISSING)
        assert "## 推荐列表" in report
        assert "600519" in report
        assert "贵州茅台" in report

    def test_criteria_conformance_section(self):
        report = build_report(RUN, JUDGEMENTS, "ROE > 15\n行业格局稳定\n无重大违规", [])
        assert "标准吻合度" in report
        assert "ROE > 15" in report
        assert "行业格局稳定" in report
        assert "无重大违规" in report  # 原文中的条目逐条出现

    def test_missing_data_section(self):
        report = build_report(RUN, JUDGEMENTS, RUN["criteria_text"], EXCLUDED_MISSING)
        assert "数据缺失" in report
        assert "688981" in report

    def test_knowledge_empty_warning(self):
        report = build_report(
            RUN, JUDGEMENTS, RUN["criteria_text"], [],
            knowledge_docs=0, has_qualitative=True,
        )
        assert "知识库为空" in report
        assert "文档中心" in report

    def test_pool_hygiene_section(self):
        report = build_report(
            RUN, JUDGEMENTS, RUN["criteria_text"], [],
            pool_stats={"st": 2, "suspended": 1, "low_liquidity": 0, "small_cap": 3},
        )
        assert "股票池卫生过滤" in report
        assert "ST/*ST/退市：2 只" in report
        assert "小市值" in report and "3 只" in report


class TestRunOverRunDiff:
    """报告尾部轮次对比：新增/移出/连续推荐。"""

    RECOMMENDED_NOW = {"600519"}  # JUDGEMENTS 中 recommend=True 的 ticker

    def test_diff_section_with_prev(self):
        report = build_report(
            RUN, JUDGEMENTS, RUN["criteria_text"], [],
            prev_recommendations={"600519", "000651"},
            prev_finished_at="2026-11-25",
        )
        assert "较上一轮（2026-11-25）" in report
        assert "新增 0 只" in report          # 600519 上一轮已有
        assert "移出 1 只" in report          # 000651 上轮有、本轮无
        assert "连续推荐 1 只" in report      # 600519

    def test_diff_all_new_when_prev_empty(self):
        report = build_report(
            RUN, JUDGEMENTS, RUN["criteria_text"], [],
            prev_recommendations=set(),
            prev_finished_at="2026-11-25",
        )
        assert "新增 1 只" in report

    def test_no_diff_section_without_prev(self):
        report = build_report(RUN, JUDGEMENTS, RUN["criteria_text"], [])
        assert "较上一轮" not in report

    def test_insufficient_section(self):
        j = {
            **JUDGEMENTS[1],
            "verdict": "insufficient",
            "reasons": ["无资料证据，无法验证护城河"],
        }
        report = build_report(RUN, [j], RUN["criteria_text"], [])
        assert "数据不足（未推荐）" in report
        assert "无资料证据" in report

    def test_failed_judgement_listed(self):
        report = build_report(RUN, JUDGEMENTS, RUN["criteria_text"], [])
        assert "000001" in report

    def test_market_cap_and_price_formatted(self):
        report = build_report(RUN, JUDGEMENTS, RUN["criteria_text"], [])
        assert "18800.00 亿" in report
        assert "1500.00" in report
        assert "1880000000000.0" not in report

    def test_no_recommendations(self):
        empty = [{**j, "recommend": False} for j in JUDGEMENTS if j["status"] == "ok"]
        report = build_report(RUN, empty, RUN["criteria_text"], [])
        assert "本次无推荐" in report


class TestThreeSectionStockLayout:
    """推荐股分区三段固定结构：量化筛选 → 事实检查 → 不推荐/存疑原因。"""

    J_REC = {
        "ticker": "600519",
        "name": "贵州茅台",
        "recommend": True,
        "reasons": [],
        "criteria_hits": [
            {
                "check": "audit_opinion", "result": "pass",
                "evidence": "年报披露无保留意见", "citation": "[1]",
                "detail": "年报披露无保留意见", "criterion": "审计意见", "hit": True,
            },
            {
                "check": "cash_coverage", "result": "not_found", "evidence": "",
                "citation": None, "detail": "缺少指标 cash_ratio",
                "criterion": "现金覆盖", "hit": False,
            },
        ],
        "confidence": 1.0,
        "snapshot": {
            "price": 1500.0, "market_cap": 1.88e12, "industry": "酿酒行业",
            "industry_percentiles": {"roe": 0.9},
        },
        "status": "ok",
    }

    def test_three_sections_present_in_order(self):
        report = build_report(RUN, [self.J_REC], RUN["criteria_text"], [])
        i1 = report.index("量化筛选")
        i2 = report.index("事实检查")
        i3 = report.index("不推荐/存疑原因")
        assert i1 < i2 < i3
        assert "年报证据" not in report

    def test_quant_section_has_values_and_percentile(self):
        report = build_report(RUN, [self.J_REC], RUN["criteria_text"], [])
        assert "18800.00 亿" in report  # _fmt_money
        assert "1500.00" in report      # _fmt_price
        assert "ROE 90%" in report      # 行业分位

    def test_fact_check_section_lists_results(self):
        report = build_report(RUN, [self.J_REC], RUN["criteria_text"], [])
        assert "审计意见：pass" in report
        assert "现金覆盖：not_found" in report

    def test_doubt_section_lists_not_found(self):
        report = build_report(RUN, [self.J_REC], RUN["criteria_text"], [])
        doubt = report[report.index("不推荐/存疑原因"):report.index("标准吻合度")]
        assert "现金覆盖" in doubt

    def test_doubt_section_nonempty_when_not_found(self):
        """not_found 场景：不推荐/存疑段必须真实非空（不能只写「无」）。"""
        report = build_report(RUN, [self.J_REC], RUN["criteria_text"], [])
        doubt = report[report.index("不推荐/存疑原因"):report.index("标准吻合度")]
        assert "- 无" not in doubt
        assert "数据不足" in doubt


class TestReportPath:
    def test_path_format(self):
        p = report_path_for("b1a2c3d4e5f67890")
        assert p.parent.name == "reports"
        # YYYY-MM-DD-<前8>.md
        name_parts = p.stem.split("-")
        assert len(name_parts[0]) == 4 and len(name_parts[1]) == 2 and len(name_parts[2]) == 2
        assert name_parts[-1] == "b1a2c3d4"
        assert p.suffix == ".md"
