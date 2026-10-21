"""LLM 标准翻译 — 自然语言标准 → 结构化规则 JSON，按文档 hash 缓存。

标准文档 hash 未变则直接读缓存（零 LLM 调用）；变了才重新翻译并 upsert。
筛选执行本身是确定性的，LLM 只在这一步（和深判）参与。
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.adapters.llm import create_llm
from core.interfaces import LLM, LLMMessage, LLMResponse
from core.logging import logger
from screener.models import ScreenerRule
from screener.rules_schema import RULES_JSON_SCHEMA, hash_criteria, validate_rules

_TRANSLATE_SYSTEM_PROMPT = (
    "你是选股规则结构化助手。用户会给出一篇自然语言的选股标准文档，"
    "你必须把它翻译成一个 JSON 对象，结构如下：\n"
    "- stock_pool: {type: 'all'|'main'|'chinext'|'star'|'watchlist', tickers: [string]} — "
    "股票池声明。type 取值：全部A股=all，沪深主板=main，创业板=chinext，科创板=star，"
    "自选公司列表=watchlist。文档明确列出个别股票代码时写入 tickers 并用 watchlist。\n"
    "- quant_rules: [{metric, op, value, missing_data_policy}] — 可量化阈值规则。"
    "metric 只能取：price/turnover/market_cap（行情快照）；revenue/net_income/gross_profit/"
    "operating_profit/rd_expense/eps/total_assets/total_liabilities/total_equity/"
    "operating_cash_flow（财务指标）；roe/gross_margin/net_margin/debt_to_equity/"
    "asset_turnover/inventory_turnover/receivables_turnover/current_ratio/quick_ratio（比率）。"
    "op ∈ {'>','>=','<','<=','=='}。missing_data_policy：该指标无数据时排除(exclude)或放行(include)，"
    "默认 exclude。\n"
    "- qualitative_criteria: [string] — 无法量化、需结合资料定性判断的条目。\n"
    "- candidate_limit: 候选深判数量上限（1-200，默认 50）。\n\n"
    "只输出 JSON，不要输出任何其他文字。无法映射到已知 metric 的量化表述放入 qualitative_criteria。"
)

_MAX_ATTEMPTS = 2  # 首次 + 重试 1 次


def _parse_llm_json(content: str) -> dict:
    """解析 LLM 输出中的 JSON（容忍 ```json 围栏）。"""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:].strip()
    return json.loads(text)


async def translate_criteria(llm: LLM, criteria_text: str) -> dict:
    """标准文本 → 结构化规则 dict。两次尝试都失败则 raise ValueError。"""
    messages = [
        LLMMessage(role="system", content=_TRANSLATE_SYSTEM_PROMPT),
        LLMMessage(role="user", content=f"选股标准文档：\n\n{criteria_text}\n\n规则 JSON Schema 参考：{json.dumps(RULES_JSON_SCHEMA, ensure_ascii=False)}"),
    ]

    last_error = ""
    for _attempt in range(_MAX_ATTEMPTS):
        response: LLMResponse = await llm.generate(messages=messages, temperature=0.1, max_tokens=2048)
        try:
            rules = _parse_llm_json(response.content)
        except (json.JSONDecodeError, AttributeError) as e:
            last_error = f"LLM 输出不是合法 JSON: {e}"
            logger.warning("标准翻译失败: %s", last_error)
            continue
        errors = validate_rules(rules)
        if errors:
            last_error = f"规则校验不过: {errors}"
            logger.warning("标准翻译校验失败: %s", last_error)
            continue
        return rules
    raise ValueError(f"标准翻译失败（{_MAX_ATTEMPTS} 次尝试）：{last_error}")


async def get_or_translate_rules(
    db: AsyncSession,
    criteria_text: str,
    llm: LLM | None = None,
) -> dict:
    """按文档 hash 查缓存；未命中则调用翻译并落 ScreenerRule。"""
    doc_hash = hash_criteria(criteria_text)
    existing = (
        await db.execute(select(ScreenerRule).where(ScreenerRule.doc_hash == doc_hash))
    ).scalar_one_or_none()
    if existing:
        return existing.rules

    rules = await translate_criteria(llm or create_llm(), criteria_text)
    db.add(ScreenerRule(doc_hash=doc_hash, rules=rules, criteria_text=criteria_text))
    await db.flush()
    return rules
