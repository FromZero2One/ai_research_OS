"""报告快照时点标注 — 可复现性：记录行情快照采集时间。"""

from __future__ import annotations

from screener.report import build_report


def _run() -> dict:
    return {"id": "r1", "candidate_count": 1, "result_count": 1}


def _judgement() -> dict:
    return {
        "ticker": "600519", "name": "贵州茅台",
        "recommend": True, "reasons": ["ok"], "criteria_hits": [],
        "confidence": 0.8, "status": "ok",
        "snapshot": {"price": 1500.0, "market_cap": 1.88e12},
    }


class TestSpotTimestamp:
    def test_report_contains_spot_time_when_given(self):
        report = build_report(_run(), [_judgement()], "标准", [], spot_taken_at="2026-10-23 09:30:00")
        assert "快照时间" in report
        assert "2026-10-23 09:30:00" in report

    def test_report_omits_spot_time_when_none(self):
        """未传快照时间（旧调用方）→ 不出现该行，向后兼容。"""
        report = build_report(_run(), [_judgement()], "标准", [])
        assert "快照时间" not in report
