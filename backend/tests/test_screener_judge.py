"""深判单测（mock LLM + fake knowledge）。"""

from __future__ import annotations

import json
from typing import Any

import pytest

from core.interfaces import LLMResponse
from screener.judge import build_judge_context, judge_candidates, judge_one

VALID_JUDGE = {
    "recommend": True,
    "reasons": ["ROE 高", "行业格局稳定"],
    "criteria_hits": [{"criterion": "ROE>15", "hit": True, "evidence": "ROE 30.2"}],
    "confidence": 0.85,
}

CAND = {
    "ticker": "600519",
    "name": "贵州茅台",
    "price": 1500.0,
    "turnover": 0.3,
    "market_cap": 1.88e12,
    "score": 0.9,
}


class FakeLLM:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content=self.responses.pop(0), model="fake", usage=None)


def _json_text(obj: dict) -> str:
    return f"```json\n{json.dumps(obj, ensure_ascii=False)}\n```"


class ExplodingKnowledge:
    async def search(self, *a: Any, **kw: Any) -> list:
        raise RuntimeError("qdrant down")


class EmptyKnowledge:
    async def search(self, *a: Any, **kw: Any) -> list:
        return []


class TestBuildContext:
    def test_includes_ticker_and_criteria(self):
        ctx = build_judge_context(CAND, ["ROE 30.2%", "毛利率 91%"])
        assert "600519" in ctx
        assert "ROE 30.2%" in ctx

    def test_empty_snippets_ok(self):
        ctx = build_judge_context(CAND, [])
        assert "600519" in ctx

    def test_includes_financial_metrics(self):
        """财务指标（ROE 等）必须出现在深判上下文里，否则 LLM 无法核对量化标准。"""
        fin = {"roe": 26.09, "gross_margin": 91.5, "net_margin": 49.4, "debt_to_equity": 15.2}
        ctx = build_judge_context(CAND, [], financials=fin)
        assert "ROE" in ctx or "roe" in ctx
        assert "26.09" in ctx
        assert "91.5" in ctx

    def test_no_financials_ok(self):
        ctx = build_judge_context(CAND, [], financials=None)
        assert "600519" in ctx


class TestJudgeOne:
    async def test_valid(self):
        llm = FakeLLM([_json_text(VALID_JUDGE)])
        out = await judge_one(llm, CAND, ["行业格局稳定"], knowledge=EmptyKnowledge())
        assert out["recommend"] is True
        assert out["confidence"] == 0.85

    async def test_knowledge_failure_silently_ignored(self):
        llm = FakeLLM([_json_text(VALID_JUDGE)])
        out = await judge_one(llm, CAND, ["x"], knowledge=ExplodingKnowledge())
        assert out["recommend"] is True  # 知识库挂了不阻塞深判

    async def test_bad_json_retries(self):
        llm = FakeLLM(["坏输出", _json_text(VALID_JUDGE)])
        out = await judge_one(llm, CAND, ["x"], knowledge=None)
        assert out["recommend"] is True
        assert llm.calls == 2

    async def test_double_failure_raises(self):
        llm = FakeLLM(["坏1", "坏2"])
        with pytest.raises(ValueError):
            await judge_one(llm, CAND, ["x"], knowledge=None)


class TestJudgeCandidates:
    async def test_failure_isolated(self):
        """单只深判失败 → 该只 status=failed，其余正常，循环不中断。"""
        ok_cand = {**CAND, "ticker": "600519"}
        bad_cand = {**CAND, "ticker": "300750", "name": "宁德时代"}

        class PickyLLM(FakeLLM):
            async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
                self.calls += 1
                # 第二只（宁德时代）返回坏输出两次（触发重试后仍失败）
                if "宁德时代" in messages[-1].content:
                    return LLMResponse(content="坏输出", model="fake", usage=None)
                return LLMResponse(content=_json_text(VALID_JUDGE), model="fake", usage=None)

        results = await judge_candidates(PickyLLM([]), [ok_cand, bad_cand], "标准文本", knowledge=None)
        assert len(results) == 2
        by_ticker = {r["ticker"]: r for r in results}
        assert by_ticker["600519"]["status"] == "ok"
        assert by_ticker["600519"]["recommend"] is True
        assert by_ticker["300750"]["status"] == "failed"
        assert by_ticker["300750"]["error"]

    async def test_transport_error_isolated(self):
        """LLM 网络异常（超时等）也只隔离单只，不拖垮整次运行。"""
        ok_cand = {**CAND, "ticker": "600519"}
        timeout_cand = {**CAND, "ticker": "300750", "name": "宁德时代"}

        class FlakyLLM(FakeLLM):
            async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
                self.calls += 1
                if "宁德时代" in messages[-1].content:
                    raise TimeoutError("LLM request timed out")
                return LLMResponse(content=_json_text(VALID_JUDGE), model="fake", usage=None)

        results = await judge_candidates(FlakyLLM([]), [ok_cand, timeout_cand], "标准文本", knowledge=None)
        by_ticker = {r["ticker"]: r for r in results}
        assert by_ticker["600519"]["status"] == "ok"
        assert by_ticker["300750"]["status"] == "failed"
        assert "timed out" in by_ticker["300750"]["error"]

    async def test_runs_concurrently(self):
        """多只候选并发深判：总耗时 ≈ 最慢单只，而非串行累加。"""
        import asyncio
        import time

        slow_cand = {**CAND, "ticker": "600519"}
        fast_cand = {**CAND, "ticker": "300750", "name": "宁德时代"}

        class SlowLLM(FakeLLM):
            async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
                self.calls += 1
                await asyncio.sleep(0.3)
                return LLMResponse(content=_json_text(VALID_JUDGE), model="fake", usage=None)

        start = time.monotonic()
        results = await judge_candidates(SlowLLM([]), [slow_cand, fast_cand], "标准文本", knowledge=None)
        elapsed = time.monotonic() - start
        assert all(r["status"] == "ok" for r in results)
        # 串行至少 0.6s；并发应 ≈ 0.3s，留余量 0.55s 判定
        assert elapsed < 0.55, f"深判疑似串行执行，耗时 {elapsed:.2f}s"

    async def test_concurrency_bounded(self):
        """并发有上限（Semaphore）：同时在途的 LLM 调用数不超过 max_concurrency。"""
        import asyncio

        cands = [{**CAND, "ticker": f"60{i:04d}", "name": f"股票{i}"} for i in range(10)]

        class TrackingLLM(FakeLLM):
            def __init__(self):
                super().__init__([])
                self.in_flight = 0
                self.max_in_flight = 0

            async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
                self.calls += 1
                self.in_flight += 1
                self.max_in_flight = max(self.max_in_flight, self.in_flight)
                try:
                    await asyncio.sleep(0.05)
                    return LLMResponse(content=_json_text(VALID_JUDGE), model="fake", usage=None)
                finally:
                    self.in_flight -= 1

        llm = TrackingLLM()
        results = await judge_candidates(llm, cands, "标准文本", knowledge=None, max_concurrency=3)
        assert len(results) == 10
        assert all(r["status"] == "ok" for r in results)
        assert llm.max_in_flight <= 3, f"并发超限：峰值 {llm.max_in_flight}"

    async def test_results_preserve_input_order(self):
        """并发后结果顺序与输入顺序一致（报告/排名依赖顺序稳定性）。"""
        cands = [{**CAND, "ticker": f"60{i:04d}", "name": f"股票{i}"} for i in range(5)]

        class IdentityLLM(FakeLLM):
            async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
                self.calls += 1
                return LLMResponse(content=_json_text(VALID_JUDGE), model="fake", usage=None)

        results = await judge_candidates(IdentityLLM([]), cands, "标准文本", knowledge=None)
        assert [r["ticker"] for r in results] == [c["ticker"] for c in cands]
