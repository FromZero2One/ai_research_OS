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
from screener.rules_schema import (
    KNOWN_METRICS,
    MONEY_METRICS,
    RULES_JSON_SCHEMA,
    UNAVAILABLE_METRICS,
    hash_criteria,
    validate_rules,
)

_AVAILABLE_METRICS_TEXT = "、".join(sorted(KNOWN_METRICS))

_TRANSLATE_SYSTEM_PROMPT = (
    "你是选股规则结构化助手。用户会给出一篇自然语言的选股标准文档，"
    "你必须把它翻译成一个 JSON 对象，结构如下：\n"
    "- stock_pool: {type: 'all'|'main'|'chinext'|'star'|'watchlist', tickers: [string]} — "
    "股票池声明。type 取值：全部A股=all，沪深主板=main，创业板=chinext，科创板=star，"
    "自选公司列表=watchlist。文档明确列出个别股票代码时写入 tickers 并用 watchlist。\n"
    "- quant_rules: [{metric, op, value, missing_data_policy}] — 可量化阈值规则。"
    f"metric 只能取以下之一：{_AVAILABLE_METRICS_TEXT}。"
    "注意：毛利额(gross_profit)、营业利润(operating_profit)、研发费用(rd_expense)、"
    "所有者权益合计(total_equity) 没有市场级数据源，遇到这类表述必须放入 "
    "qualitative_criteria。op ∈ {'>','>=','<','<=','=='}。missing_data_policy："
    "该指标无数据时排除(exclude)或放行(include)，默认 exclude。"
    "单位约定：金额类指标（market_cap/revenue/net_income/operating_cash_flow/"
    "total_assets/total_liabilities）必须同时输出 value_unit（'元'/'万'/'亿'），"
    "value 填原始数字，不要自行换算成元的数量级——『市值100亿』输出 "
    "{value: 100, value_unit: '亿'}，『营收50亿』输出 {value: 50, value_unit: '亿'}。"
    "百分比指标（roe/gross_margin/net_margin/debt_to_equity/revenue_growth/"
    "net_income_growth/turnover）填百分数并标 value_unit='%'（『ROE>15%』→ value=15）；"
    "周转率/流动比率/速动比率以及 pe/pb/ps 标 value_unit='倍'；"
    "price/eps 标 value_unit='元'。\n"
    "- qualitative_criteria: [string] — 无法量化、需结合资料定性判断的条目。\n"
    "- candidate_limit: 候选深判数量上限（1-200，默认 50）。\n\n"
    "只输出 JSON，不要输出任何其他文字。无法映射到已知 metric 的量化表述放入 qualitative_criteria。"
)

_MAX_ATTEMPTS = 2  # 首次 + 重试 1 次


_MONEY_MULTIPLIER = {"元": 1.0, "万": 1e4, "亿": 1e8}


def _normalize_units(rules: dict) -> dict:
    """把 LLM 输出的 value + value_unit 换算成规则求值用的基础单位。

    金额统一换算为「元」，百分比/倍数保持数字不变。这样模型只需填 100+亿，
    不用自己数零；下游 screening/preset 规则仍看到与内置预设一致的元值。
    """
    quant_rules: list = []
    for rule in rules.get("quant_rules") or []:
        if not isinstance(rule, dict):
            quant_rules.append(rule)
            continue
        normalized = dict(rule)
        unit = normalized.pop("value_unit", None)
        value = normalized.get("value")
        multiplier = _MONEY_MULTIPLIER.get(unit)
        if (
            multiplier is not None
            and normalized.get("metric") in MONEY_METRICS
            and isinstance(value, (int, float))
            and not isinstance(value, bool)
        ):
            normalized["value"] = float(value) * multiplier
        quant_rules.append(normalized)
    return {**rules, "quant_rules": quant_rules}


def _downgrade_unavailable_metrics(rules: dict) -> tuple[dict, list[str]]:
    """把命中「无市场级数据源」指标的量化规则降级为定性条目。

    LLM 经常无视提示词继续输出 rd_expense 等键；直接让 run 失败体验太硬，
    降级后该条目仍会进入深判与报告，用户能看到「需结合资料判断」而不是得到
    一个静默的 0 候选。返回 (新规则, 被降级的描述列表)。
    """
    quant_rules = rules.get("quant_rules") or []
    kept: list[dict] = []
    downgraded: list[str] = []
    for rule in quant_rules:
        if isinstance(rule, dict) and rule.get("metric") in UNAVAILABLE_METRICS:
            downgraded.append(
                f"{rule.get('metric')} {rule.get('op')} {rule.get('value')}"
                "（该指标暂无市场级数据源，需结合资料判断）"
            )
        else:
            kept.append(rule)
    if not downgraded:
        return rules, []
    qualitative = list(rules.get("qualitative_criteria") or []) + downgraded
    return {**rules, "quant_rules": kept, "qualitative_criteria": qualitative}, downgraded


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
    schema_text = json.dumps(RULES_JSON_SCHEMA, ensure_ascii=False)
    messages = [
        LLMMessage(role="system", content=_TRANSLATE_SYSTEM_PROMPT),
        LLMMessage(
            role="user",
            content=f"选股标准文档：\n\n{criteria_text}\n\n规则 JSON Schema 参考：{schema_text}",
        ),
    ]

    last_error = ""
    for _attempt in range(_MAX_ATTEMPTS):
        response: LLMResponse = await llm.generate(
            messages=messages, temperature=0.1, max_tokens=2048
        )
        try:
            rules = _parse_llm_json(response.content)
        except (json.JSONDecodeError, AttributeError) as e:
            last_error = f"LLM 输出不是合法 JSON: {e}"
            logger.warning("标准翻译失败: %s", last_error)
            continue
        rules = _normalize_units(rules)
        rules, downgraded = _downgrade_unavailable_metrics(rules)
        if downgraded:
            logger.warning("指标无市场级数据源，已降级为定性标准: %s", downgraded)
        errors = validate_rules(rules)
        if errors:
            last_error = f"规则校验不过: {errors}"
            logger.warning("标准翻译校验失败: %s", last_error)
            continue
        return rules
    raise ValueError(f"标准翻译失败（{_MAX_ATTEMPTS} 次尝试）：{last_error}")


def _stale_metrics(rules: dict) -> list[str]:
    """缓存规则中使用已不再可用指标的键（指标白名单变更后的旧缓存）。"""
    quant_rules = rules.get("quant_rules") or []
    return sorted(
        {
            r.get("metric")
            for r in quant_rules
            if isinstance(r, dict) and r.get("metric") not in KNOWN_METRICS
        }
    )


async def get_or_translate_rules(
    db: AsyncSession,
    criteria_text: str,
    llm: LLM | None = None,
) -> dict:
    """按文档 hash 查缓存；未命中或缓存含不可用指标时重新翻译并落库。"""
    doc_hash = hash_criteria(criteria_text)
    existing = (
        await db.execute(select(ScreenerRule).where(ScreenerRule.doc_hash == doc_hash))
    ).scalar_one_or_none()
    if existing:
        stale = _stale_metrics(existing.rules or {})
        if not stale:
            return existing.rules
        logger.warning("标准缓存含已不可用指标 %s，重新翻译（hash=%s）", stale, doc_hash)
        await db.delete(existing)
        await db.flush()

    rules = await translate_criteria(llm or create_llm(), criteria_text)
    db.add(ScreenerRule(doc_hash=doc_hash, rules=rules, criteria_text=criteria_text))
    await db.flush()
    return rules
