"""LLM 标准翻译单测（mock LLM + 缓存逻辑）。"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.interfaces import LLMResponse
from screener.models import ScreenerRule
from screener.translate import get_or_translate_rules, translate_criteria
from screener.rules_schema import hash_criteria

VALID_RULES = {
    "stock_pool": {"type": "all", "tickers": []},
    "quant_rules": [{"metric": "roe", "op": ">", "value": 15.0, "missing_data_policy": "exclude"}],
    "qualitative_criteria": ["行业格局稳定"],
    "candidate_limit": 50,
}


class FakeLLM:
    """按预设响应序列返回的假 LLM。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0

    async def generate(self, messages: Any, **kwargs: Any) -> LLMResponse:
        self.calls += 1
        return LLMResponse(content=self.responses.pop(0), model="fake", usage=None)


def _json_text(obj: dict) -> str:
    import json

    return f"```json\n{json.dumps(obj, ensure_ascii=False)}\n```"


class TestTranslateCriteria:
    async def test_valid_json(self):
        llm = FakeLLM([_json_text(VALID_RULES)])
        rules = await translate_criteria(llm, "ROE>15")
        assert rules["stock_pool"]["type"] == "all"
        assert llm.calls == 1

    async def test_retry_on_bad_then_good(self):
        llm = FakeLLM(["这不是 JSON", _json_text(VALID_RULES)])
        rules = await translate_criteria(llm, "ROE>15")
        assert rules["candidate_limit"] == 50
        assert llm.calls == 2

    async def test_double_failure_raises(self):
        llm = FakeLLM(["坏输出1", _json_text({"stock_pool": {"type": "nope"}})])
        with pytest.raises(ValueError):
            await translate_criteria(llm, "ROE>15")


class TestGetOrTranslateRules:
    async def test_cache_hit_skips_llm(self, test_session: AsyncSession):
        text = "ROE>15"
        test_session.add(
            ScreenerRule(
                doc_hash=hash_criteria(text),
                rules={"stock_pool": {"type": "main", "tickers": []}, "quant_rules": [],
                       "qualitative_criteria": [], "candidate_limit": 50},
                criteria_text=text,
            )
        )
        await test_session.flush()

        llm = FakeLLM([])
        rules = await get_or_translate_rules(test_session, text, llm=llm)
        assert rules["stock_pool"]["type"] == "main"
        assert llm.calls == 0  # 缓存命中，零 LLM 调用

    async def test_cache_miss_translates_and_saves(self, test_session: AsyncSession):
        text = "市值大于100亿"
        llm = FakeLLM([_json_text(VALID_RULES)])
        rules = await get_or_translate_rules(test_session, text, llm=llm)
        assert llm.calls == 1
        assert rules["candidate_limit"] == 50

        from sqlalchemy import select

        saved = (
            await test_session.execute(select(ScreenerRule).where(ScreenerRule.doc_hash == hash_criteria(text)))
        ).scalar_one()
        assert saved.rules["candidate_limit"] == 50
