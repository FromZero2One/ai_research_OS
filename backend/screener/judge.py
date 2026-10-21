"""深判 — LLM 对初筛通过的候选逐只定性判断（单只失败不拖垮整次运行）。

判断依据：行情/财务快照 + 可选知识库片段（检索失败静默省略）。
LLM 只能依据提供的上下文判断，不得编造数字。
"""

from __future__ import annotations

import json

from core.interfaces import LLM, LLMMessage, LLMResponse
from core.logging import logger

JUDGE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "recommend": {"type": "boolean"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "criteria_hits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion": {"type": "string"},
                    "hit": {"type": "boolean"},
                    "evidence": {"type": "string"},
                },
                "required": ["criterion", "hit"],
            },
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["recommend", "reasons", "criteria_hits", "confidence"],
}

_JUDGE_SYSTEM_PROMPT = (
    "你是投资研究分析师。给定一只股票的数据快照和一组定性选股标准，逐条判断该股票是否符合标准。\n"
    "规则：\n"
    "1. 只依据提供的上下文判断，不得编造任何数字或事实；\n"
    "2. 上下文不足以判断某条标准时，该条 hit=false 并在 evidence 写明'数据不足'；\n"
    "3. 输出 JSON：{recommend: bool, reasons: [string], "
    "criteria_hits: [{criterion, hit, evidence}], confidence: 0-1}。\n"
    "只输出 JSON。"
)

_MAX_ATTEMPTS = 2


_METRIC_CN = {
    "roe": "ROE(%)", "gross_margin": "毛利率(%)", "net_margin": "净利率(%)",
    "debt_to_equity": "负债/权益(%)", "current_ratio": "流动比率(倍)",
    "operating_cash_flow": "经营现金流(元)", "revenue": "营业总收入(元)",
    "net_income": "净利润(元)", "total_assets": "总资产(元)", "total_liabilities": "总负债(元)",
    "eps": "每股收益(元)", "market_cap": "总市值(元)",
}


def build_judge_context(
    candidate: dict,
    knowledge_snippets: list[str],
    financials: dict[str, float] | None = None,
) -> str:
    """拼装单只候选的判断上下文（纯函数）。

    financials 为该候选最新一期的财务指标（metric → value），
    LLM 需要它来核对量化标准；缺数据时明确标注"无"而非留空。
    """
    lines = [
        f"股票: {candidate.get('name')}（{candidate.get('ticker')}）",
        f"行情快照: 现价 {candidate.get('price')}, 换手率 {candidate.get('turnover')}, "
        f"总市值 {candidate.get('market_cap')}, 初筛得分 {candidate.get('score')}",
    ]
    if financials:
        parts = [f"{_METRIC_CN.get(k, k)}={v}" for k, v in financials.items() if v is not None]
        if parts:
            lines.append(f"财务指标（最新报告期）: {'; '.join(parts)}")
        else:
            lines.append("财务指标（最新报告期）: 无")
    else:
        lines.append("财务指标（最新报告期）: 无")
    if knowledge_snippets:
        lines.append("相关资料片段：")
        for i, snippet in enumerate(knowledge_snippets, 1):
            lines.append(f"[{i}] {snippet[:300]}")
    else:
        lines.append("（无可用资料片段）")
    return "\n".join(lines)


def _parse_llm_json(content: str) -> dict:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
        text = text.rsplit("```", 1)[0]
    if text.startswith("json"):
        text = text[4:].strip()
    return json.loads(text)


async def judge_one(
    llm: LLM,
    candidate: dict,
    criteria: list[str],
    knowledge=None,
    financials: dict[str, float] | None = None,
) -> dict:
    """单只候选深判。两次尝试都失败 raise ValueError（调用方决定隔离策略）。"""
    # 知识库检索：失败静默吞掉（资料是加分项，不是必需品）
    snippets: list[str] = []
    if knowledge is not None:
        try:
            results = await knowledge.search(candidate["name"], top_k=3)
            snippets = [getattr(r, "content", str(r)) for r in results]
        except Exception as e:  # noqa: BLE001 — 检索故障不阻塞深判
            logger.warning("深判知识库检索失败 %s: %s", candidate["ticker"], e)

    user_msg = (
        f"{build_judge_context(candidate, snippets, financials=financials)}\n\n"
        f"定性标准：\n" + "\n".join(f"- {c}" for c in criteria)
    )
    messages = [
        LLMMessage(role="system", content=_JUDGE_SYSTEM_PROMPT),
        LLMMessage(role="user", content=user_msg),
    ]

    last_error = ""
    for _attempt in range(_MAX_ATTEMPTS):
        response: LLMResponse = await llm.generate(messages=messages, temperature=0.2, max_tokens=1024)
        try:
            out = _parse_llm_json(response.content)
            assert isinstance(out.get("recommend"), bool)
            assert isinstance(out.get("confidence"), (int, float))
        except (json.JSONDecodeError, AttributeError, AssertionError) as e:
            last_error = f"LLM 输出解析失败: {e}"
            continue
        return out
    raise ValueError(last_error)


async def judge_candidates(
    llm: LLM,
    candidates: list[dict],
    criteria_text: str,
    knowledge=None,
    qualitative: list[str] | None = None,
    financials_by_ticker: dict[str, list] | None = None,
) -> list[dict]:
    """逐只深判；单只 ValueError → 该只 status=failed，循环继续。

    qualitative 为结构化规则里的定性条目；未提供时退回用标准原文整段判断。
    financials_by_ticker 提供候选的最新财务指标（进入深判上下文）。
    """
    criteria = qualitative or [criteria_text]

    results: list[dict] = []
    for cand in candidates:
        # 最新一期财务指标 → 简化 dict（metric → value）
        fin: dict[str, float] | None = None
        if financials_by_ticker:
            entries = financials_by_ticker.get(cand["ticker"]) or []
            best: dict[str, tuple] = {}
            for e in entries:
                if e.metric_value is None:
                    continue
                key = (e.fiscal_year, e.fiscal_period)
                if e.metric_name not in best or key > best[e.metric_name][0]:
                    best[e.metric_name] = (key, e.metric_value)
            fin = {k: v[1] for k, v in best.items()} if best else None
        try:
            judgement = await judge_one(llm, cand, criteria or [criteria_text], knowledge=knowledge, financials=fin)
            results.append(
                {
                    "ticker": cand["ticker"],
                    "name": cand["name"],
                    "recommend": judgement["recommend"],
                    "reasons": judgement.get("reasons", []),
                    "criteria_hits": judgement.get("criteria_hits", []),
                    "confidence": judgement.get("confidence"),
                    "snapshot": {k: cand.get(k) for k in ("price", "turnover", "market_cap", "score")},
                    "status": "ok",
                    "error": None,
                }
            )
        except ValueError as e:
            logger.warning("深判失败 %s: %s", cand["ticker"], e)
            results.append(
                {
                    "ticker": cand["ticker"],
                    "name": cand["name"],
                    "recommend": None,
                    "reasons": [],
                    "criteria_hits": [],
                    "confidence": None,
                    "snapshot": {k: cand.get(k) for k in ("price", "turnover", "market_cap", "score")},
                    "status": "failed",
                    "error": str(e),
                }
            )
        except Exception as e:  # noqa: BLE001 — 网络超时等传输故障同样只隔离单只
            logger.warning("深判异常 %s: %s", cand["ticker"], e)
            results.append(
                {
                    "ticker": cand["ticker"],
                    "name": cand["name"],
                    "recommend": None,
                    "reasons": [],
                    "criteria_hits": [],
                    "confidence": None,
                    "snapshot": {k: cand.get(k) for k in ("price", "turnover", "market_cap", "score")},
                    "status": "failed",
                    "error": f"LLM 调用异常: {e}",
                }
            )
    return results
