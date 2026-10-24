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


class TestReportPath:
    def test_path_format(self):
        p = report_path_for("b1a2c3d4e5f67890")
        assert p.parent.name == "reports"
        # YYYY-MM-DD-<前8>.md
        name_parts = p.stem.split("-")
        assert len(name_parts[0]) == 4 and len(name_parts[1]) == 2 and len(name_parts[2]) == 2
        assert name_parts[-1] == "b1a2c3d4"
        assert p.suffix == ".md"
