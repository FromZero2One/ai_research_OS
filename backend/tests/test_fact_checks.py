"""事实检查确定性化单测（mock knowledge / financials，零 LLM）。"""

from __future__ import annotations

from types import SimpleNamespace

from screener.fact_checks import apply_fact_check_verdict, run_fact_checks


class FakeKnowledge:
    """按 query 关键词返回预设片段，记录调用参数。"""

    def __init__(self, results: dict[str, list[str]] | None = None, error: bool = False):
        self.results = results or {}
        self.error = error
        self.calls: list[dict] = []

    async def search(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        if self.error:
            raise RuntimeError("qdrant down")
        for key, snippets in self.results.items():
            if key in query:
                return [SimpleNamespace(content=s) for s in snippets]
        return []


def _result(check: str) -> dict:
    return next(r for r in _RESULTS if r["check"] == check)


_RESULTS: list[dict] = []


def _run(checks, knowledge, financials=None):
    global _RESULTS
    _RESULTS = run_fact_checks_sync(checks, knowledge, "cid", financials or {})
    return _RESULTS


def run_fact_checks_sync(checks, knowledge, company_id, financials):
    import asyncio

    return asyncio.run(run_fact_checks(checks, knowledge, company_id, financials))


AUDIT_CHECK = {"check": "audit_opinion"}
LITIGATION_CHECK = {"check": "litigation"}
CASH_CHECK = {"check": "cash_coverage", "threshold": 1.0, "metric": "cash_ratio"}


class TestAuditOpinion:
    def test_unqualified_opinion_passes_with_citation(self):
        kb = FakeKnowledge(
            {
                "审计": [
                    "公司 2024 年度财务报表经立信会计师事务所审计，出具了标准无保留意见报告。"
                ],
            }
        )
        out = _run([AUDIT_CHECK], kb)
        assert out[0]["result"] == "pass"
        assert out[0]["citation"] == "[1]"

    def test_qualified_opinion_fails(self):
        kb = FakeKnowledge({"审计": ["会计师事务所对本公司出具了保留意见的审计报告。"]})
        out = _run([AUDIT_CHECK], kb)
        assert out[0]["result"] == "fail"


class TestLitigation:
    def test_litigation_hit_fails(self):
        kb = FakeKnowledge({"诉讼": ["报告期内公司存在重大诉讼事项，并收到证监会行政处罚决定书。"]})
        out = _run([LITIGATION_CHECK], kb)
        assert out[0]["result"] == "fail"

    def test_zero_hits_not_found(self):
        kb = FakeKnowledge({})
        out = _run([LITIGATION_CHECK], kb)
        assert out[0]["result"] == "not_found"


class TestCashCoverage:
    def test_computed_from_financials(self):
        out = _run([CASH_CHECK], FakeKnowledge({}), financials={"cash_ratio": 1.8})
        assert out[0]["result"] == "pass"
        assert "1.8" in out[0]["detail"]

    def test_below_threshold_fails(self):
        out = _run([CASH_CHECK], FakeKnowledge({}), financials={"cash_ratio": 0.3})
        assert out[0]["result"] == "fail"

    def test_missing_metric_not_found(self):
        out = _run([CASH_CHECK], FakeKnowledge({}), financials={})
        assert out[0]["result"] == "not_found"


class TestRobustness:
    def test_retrieval_failure_swallowed_as_not_found(self):
        out = _run([AUDIT_CHECK], FakeKnowledge(error=True))
        assert out[0]["result"] == "not_found"

    def test_order_preserved(self):
        checks = [CASH_CHECK, AUDIT_CHECK, LITIGATION_CHECK]
        out = _run(checks, FakeKnowledge({}), financials={"cash_ratio": 2.0})
        assert [r["check"] for r in out] == ["cash_coverage", "audit_opinion", "litigation"]


class TestVerdictSynthesis:
    """纯三态判定：fail→reject、not_found→insufficient、全 pass→recommend（无 LLM 结论合并）。"""

    def test_fail_rejects(self):
        facts = [{"check": "audit_opinion", "result": "fail"}]
        out = apply_fact_check_verdict(facts)
        assert out["recommend"] is False
        assert out["verdict"] == "reject"
        assert out["reasons"]

    def test_not_found_insufficient(self):
        facts = [{"check": "audit_opinion", "result": "not_found"}]
        out = apply_fact_check_verdict(facts)
        assert out["verdict"] == "insufficient"
        assert out["recommend"] is False

    def test_reject_beats_insufficient(self):
        facts = [
            {"check": "audit_opinion", "result": "not_found"},
            {"check": "litigation", "result": "fail"},
        ]
        out = apply_fact_check_verdict(facts)
        assert out["verdict"] == "reject"

    def test_all_pass_recommends(self):
        facts = [{"check": "audit_opinion", "result": "pass"}]
        out = apply_fact_check_verdict(facts)
        assert out["verdict"] == "recommend"
        assert out["recommend"] is True

    def test_empty_facts_recommends(self):
        out = apply_fact_check_verdict([])
        assert out["verdict"] == "recommend"
        assert out["recommend"] is True
