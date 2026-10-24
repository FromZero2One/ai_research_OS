"""深判评测器单测 — 用例加载、证据纪律评分、端到端 fake LLM。"""

from __future__ import annotations

import json
from typing import Any

from core.interfaces import LLMResponse
from screener.judge_eval import load_cases, run_case, score_case, summarize


class FakeLLM:
    def __init__(self, payload: dict):
        self.payload = payload

    async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
        return LLMResponse(
            content=f"```json\n{json.dumps(self.payload, ensure_ascii=False)}\n```",
            model="fake",
            usage=None,
        )


def _judgement(**overrides) -> dict:
    base = {
        "recommend": True,
        "reasons": ["测试"],
        "criteria_hits": [],
        "confidence": 0.8,
    }
    base.update(overrides)
    return base


class TestScoreCase:
    def test_doc_only_hit_without_snippets_is_violation(self):
        case = {"id": "x", "snippets": [], "expected": {"recommend": False}}
        judgement = _judgement(
            recommend=False,
            criteria_hits=[{"criterion": "存在护城河", "hit": True, "evidence": "行业龙头"}],
        )
        result = score_case(case, judgement, 1.0)
        assert any("doc_only_without_snippets" in v for v in result.violations)
        assert result.recommend_match is True

    def test_snippet_hit_requires_citation(self):
        case = {"id": "x", "snippets": ["品牌壁垒显著"]}
        judgement = _judgement(
            criteria_hits=[{"criterion": "存在护城河", "hit": True, "evidence": "品牌壁垒"}]
        )
        result = score_case(case, judgement, 1.0)
        assert any("missing_citation" in v for v in result.violations)

    def test_financial_hit_with_number_ok(self):
        case = {"id": "x", "snippets": []}
        judgement = _judgement(
            criteria_hits=[{"criterion": "现金充裕", "hit": True, "evidence": "流动比率 4.0 倍"}]
        )
        result = score_case(case, judgement, 1.0)
        assert result.violations == []

    def test_summary_counts(self):
        case = {"id": "x", "snippets": [], "expected": {"recommend": False}}
        bad = score_case(
            case,
            _judgement(
                recommend=False,
                criteria_hits=[{"criterion": "无重大违规", "hit": True, "evidence": "未发现"}],
            ),
            1.0,
        )
        good = score_case(case, _judgement(recommend=False), 1.0)
        summary = summarize([bad, good])
        assert summary["cases"] == 2
        assert summary["json_valid_rate"] == 1.0
        assert summary["recommend_match"] == 2
        assert summary["cases_with_violations"] == 1


async def test_run_case_uses_evidence_guard():
    case = {
        "id": "doc_no_knowledge",
        "ticker": "600519",
        "name": "贵州茅台",
        "criteria": ["存在护城河"],
        "snippets": [],
        "financials": {"roe": 30.0},
        "expected": {"recommend": False},
    }
    llm = FakeLLM(_judgement(
        recommend=True,
        criteria_hits=[{"criterion": "存在护城河", "hit": True, "evidence": "行业龙头"}],
    ))
    result = await run_case(llm, case)
    assert result.status == "ok"
    assert result.recommend is False  # 证据守卫强制否决
    assert result.recommend_match is True
    assert result.downgraded == 1


def test_default_cases_load():
    cases = load_cases()
    assert len(cases) >= 10
    ids = {c["id"] for c in cases}
    assert "doc_moat_no_knowledge" in ids
