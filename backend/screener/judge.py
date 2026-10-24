"""深判 — LLM 对初筛通过的候选逐只定性判断（单只失败不拖垮整次运行）。

判断依据：行情/财务快照 + 可选知识库片段（检索失败静默省略）。
LLM 只能依据提供的上下文判断，不得编造数字。
"""

from __future__ import annotations

import asyncio
import json
import re

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
    "criteria_hits: [{criterion, hit, evidence}], confidence: 0-1}；\n"
    "4. 输出尽量精简：reasons 最多 5 条、每条不超过 50 字；criteria_hits 的 evidence "
    "不超过 40 字，禁止整段复述上下文；\n"
    "5. 定性标准必须基于上下文中的资料片段：命中时 evidence 必须引用片段编号（如 [1]）"
    "或上下文里的具体数字；无资料片段、资料未提及或只有常识/行业印象时，必须 hit=false "
    "并写'数据不足'，禁止用模型记忆补全；\n"
    "6. 不得把'资料中未出现负面信息'当作'无违规/无风险'——缺失信息不等于通过；\n"
    "7. criteria_hits 的 criterion 必须逐字复制给定的定性标准原文，不得改写成预设名"
    "或自拟标签。\n"
    "只输出 JSON。"
)

_MAX_ATTEMPTS = 2
# 1024 会让 criteria_hits 较长的候选在 JSON 中途被截断。首轮给足空间，
# 重试再放大并附带"压缩输出"提示，避免用同样的参数重复失败。
_JUDGE_MAX_TOKENS = 2560
_JUDGE_RETRY_MAX_TOKENS = 3584
_RETRY_HINT = LLMMessage(
    role="user",
    content=(
        "上次输出不是合法 JSON（通常是被截断）。请重新输出：只输出 JSON，并进一步压缩——"
        "reasons 最多 3 条、每条不超过 40 字；criteria_hits 的 evidence 不超过 25 字。"
    ),
)


# 需要文档/外部资料才能判断的标准关键词。无资料片段时，这些条目的 hit=true
# 一律降级（模型很容易用"行业龙头暗示护城河"之类先验知识补全）。
_DOC_ONLY_HINTS = (
    "违规", "诉讼", "处罚", "治理", "管理层", "股东回报", "分红", "回购",
    "护城河", "品牌", "专利", "壁垒", "行业", "渗透率", "排名", "周期",
    "产能", "主营", "战略", "政策", "监管", "持续",
)


def _is_doc_only(criterion: str) -> bool:
    return any(hint in criterion for hint in _DOC_ONLY_HINTS)


def _apply_evidence_guard(judgement: dict, snippets: list[str]) -> dict:
    """后置证据校验：没有可核验证据的命中一律降级，并否决 recommend。

    - 有资料片段：hit=true 的 evidence 必须引用 [n]
    - 无资料片段：文档类标准直接判 false；可由财务数字判断的标准要求 evidence 含数字
    这是对 LLM「用先验知识/缺失信息当通过」的确定性兜底。
    """
    hits = judgement.get("criteria_hits") or []
    downgraded: list[str] = []
    guarded: list = []
    for hit in hits:
        if not isinstance(hit, dict):
            guarded.append(hit)
            continue
        criterion = str(hit.get("criterion") or "")
        evidence = str(hit.get("evidence") or "")
        if hit.get("hit"):
            if snippets:
                grounded = bool(re.search(r"\[\d+\]", evidence))
            elif _is_doc_only(criterion):
                grounded = False
            else:
                grounded = bool(re.search(r"\d", evidence))
            if not grounded:
                downgraded.append(criterion or "未命名标准")
                hit = {**hit, "hit": False, "evidence": "无资料证据，无法验证（自动降级）"}
        guarded.append(hit)
    if not downgraded:
        return judgement
    # 放在最前面：报告“未推荐”列表只取前两条理由，必须让用户先看到降级原因
    reasons = [
        "以下定性标准缺少可核验证据，已自动判定为不满足：" + "、".join(downgraded),
        *list(judgement.get("reasons") or []),
    ]
    return {
        **judgement,
        "criteria_hits": guarded,
        "recommend": False,
        "confidence": min(float(judgement.get("confidence") or 0.0), 0.4),
        "reasons": reasons,
    }


_METRIC_CN = {
    "price": "现价", "turnover": "换手率", "market_cap": "总市值",
    "roe": "ROE", "gross_margin": "毛利率", "net_margin": "净利率",
    "debt_to_equity": "负债/权益", "current_ratio": "流动比率", "quick_ratio": "速动比率",
    "asset_turnover": "总资产周转率", "inventory_turnover": "存货周转率",
    "receivables_turnover": "应收账款周转率",
    "operating_cash_flow": "经营现金流", "revenue": "营业总收入", "net_income": "净利润",
    "revenue_growth": "营收同比", "net_income_growth": "净利同比",
    "total_assets": "总资产", "total_liabilities": "总负债", "eps": "每股收益",
}

_MONEY_METRICS = frozenset({
    "market_cap", "operating_cash_flow", "revenue", "net_income",
    "total_assets", "total_liabilities",
})
_PERCENT_METRICS = frozenset({
    "roe", "gross_margin", "net_margin", "debt_to_equity",
    "revenue_growth", "net_income_growth", "turnover",
})
_RATIO_METRICS = frozenset({
    "current_ratio", "quick_ratio", "asset_turnover",
    "inventory_turnover", "receivables_turnover",
})
# 比率类指标的常见区间；越界提示 LLM 标注异常，避免把一次性损益当成经营信号
_ANOMALY_BOUNDS = {"net_margin": (-100.0, 100.0), "gross_margin": (-100.0, 100.0), "roe": (-100.0, 100.0)}


def _fmt_money(value: float) -> str:
    """金额统一成亿/万元，避免 LLM 对原始元值做单位换算时出错。"""
    v = float(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿元"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f}万元"
    return f"{v:.2f}元"


def _fmt_value(metric: str, value: float) -> str:
    """按指标类型附带单位（金额/百分比/倍数/元）。"""
    if metric in _MONEY_METRICS:
        return _fmt_money(value)
    if metric in _PERCENT_METRICS:
        return f"{float(value):.2f}%"
    if metric in _RATIO_METRICS:
        return f"{float(value):.2f}倍"
    if metric in {"price", "eps"}:
        return f"{float(value):.2f}元"
    return f"{value}"


def _anomaly_notes(financials: dict[str, float]) -> list[str]:
    """越界比率提示（净利率 176% 这类值必须让 LLM 知道是异常，而非经营信号）。"""
    notes: list[str] = []
    for metric, (lo, hi) in _ANOMALY_BOUNDS.items():
        value = financials.get(metric)
        if value is None:
            continue
        try:
            fv = float(value)
        except (TypeError, ValueError):
            continue
        if fv < lo or fv > hi:
            label = _METRIC_CN.get(metric, metric)
            notes.append(
                f"{label}={fv:.2f}% 超出常见区间，可能含大额投资收益/一次性损益或口径差异，"
                "判断时请标注为异常并谨慎解读"
            )
    return notes


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_judge_context(
    candidate: dict,
    knowledge_snippets: list[str],
    financials: dict[str, float] | None = None,
) -> str:
    """拼装单只候选的判断上下文（纯函数）。

    financials 为该候选最新一期的财务指标（metric → value），
    LLM 需要它来核对量化标准；缺数据时明确标注"无"而非留空。
    金额/比率一律带单位输出，降低模型单位换算出错的空间。
    """
    price = _as_float(candidate.get("price"))
    turnover = _as_float(candidate.get("turnover"))
    market_cap = _as_float(candidate.get("market_cap"))
    industry = candidate.get("industry")
    sector = candidate.get("sector")
    lines = [
        f"股票: {candidate.get('name')}（{candidate.get('ticker')}）",
        f"行业: {industry or '未知'}"
        + (
            "（金融行业：流动比率、毛利率、周转率等指标口径不适用）"
            if sector == "financial" else ""
        ),
        f"行情快照: 现价 {_fmt_money(price) if price is not None else '-'}, "
        f"换手率 {f'{turnover:.2f}%' if turnover is not None else '-'}, "
        f"总市值 {_fmt_money(market_cap) if market_cap is not None else '-'}, "
        f"初筛得分 {candidate.get('score')}",
    ]
    # union 初筛命中的预设（LLM 聚焦定性判断 + 复核异常，而非重新验证数字）
    preset_names = candidate.get("presets")
    if preset_names:
        lines.append(f"命中预设: {'、'.join(preset_names)}（命中 {candidate.get('hits', len(preset_names))} 套）")
    if financials:
        parts = [
            f"{_METRIC_CN.get(k, k)}={_fmt_value(k, v)}"
            for k, v in financials.items()
            if v is not None and _as_float(v) is not None
        ]
        if parts:
            lines.append(f"财务指标（最新报告期）: {'; '.join(parts)}")
        else:
            lines.append("财务指标（最新报告期）: 无")
        notes = _anomaly_notes(financials)
        if notes:
            lines.append("数据异常提示: " + "；".join(notes))
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
    # 容忍 JSON 前后附着解释文字（取第一个 { 到最后一个 }）
    if not text.startswith("{"):
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            text = text[start : end + 1]
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
            query = f"{candidate.get('name', '')} {candidate.get('ticker', '')}".strip()
            if criteria:
                query += " " + " ".join(str(c)[:30] for c in criteria[:2])
            results = await knowledge.search(query, top_k=3)
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
    for attempt in range(_MAX_ATTEMPTS):
        # 截断是确定性的：重试时放大 token 预算并明确要求压缩输出
        attempt_messages = messages if attempt == 0 else [*messages, _RETRY_HINT]
        max_tokens = _JUDGE_MAX_TOKENS if attempt == 0 else _JUDGE_RETRY_MAX_TOKENS
        response: LLMResponse = await llm.generate(
            messages=attempt_messages, temperature=0.2, max_tokens=max_tokens
        )
        try:
            out = _parse_llm_json(response.content)
            assert isinstance(out.get("recommend"), bool)
            assert isinstance(out.get("confidence"), (int, float))
        except (json.JSONDecodeError, AttributeError, AssertionError) as e:
            last_error = f"LLM 输出解析失败: {e}"
            continue
        return _apply_evidence_guard(out, snippets)
    raise ValueError(last_error)


# 深判默认并发数：单用户 DeepSeek 云端，5 路并发不触发限流
_DEFAULT_MAX_CONCURRENCY = 5


async def judge_candidates(
    llm: LLM,
    candidates: list[dict],
    criteria_text: str,
    knowledge=None,
    qualitative: list[str] | None = None,
    financials_by_ticker: dict[str, list] | None = None,
    max_concurrency: int = _DEFAULT_MAX_CONCURRENCY,
) -> list[dict]:
    """并发深判；单只失败 → 该只 status=failed，其余不受影响。

    qualitative 为结构化规则里的定性条目；未提供时退回用标准原文整段判断。
    financials_by_ticker 提供候选的最新财务指标（进入深判上下文）。
    max_concurrency 限制同时在途的 LLM 调用数（Semaphore）。
    结果顺序与输入顺序一致（asyncio.gather 保序）。
    """
    criteria = qualitative or [criteria_text]
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _judge_with_limits(cand: dict) -> dict:
        async with semaphore:
            return await _judge_single(
                llm, cand, criteria, criteria_text, knowledge, financials_by_ticker
            )

    return list(await asyncio.gather(*(_judge_with_limits(c) for c in candidates)))


def _snapshot_fields(cand: dict) -> dict:
    """深判结果透传的行情/初筛/行业快照字段。"""
    return {
        k: cand.get(k)
        for k in (
            "price", "turnover", "market_cap", "score", "hits", "presets",
            "industry", "sector",
        )
        if cand.get(k) is not None
    }


def _failed_judgement(cand: dict, error: str) -> dict:
    return {
        "ticker": cand["ticker"],
        "name": cand["name"],
        "recommend": None,
        "reasons": [],
        "criteria_hits": [],
        "confidence": None,
        "snapshot": _snapshot_fields(cand),
        "status": "failed",
        "error": error,
    }


async def _judge_single(
    llm: LLM,
    cand: dict,
    criteria: list[str],
    criteria_text: str,
    knowledge=None,
    financials_by_ticker: dict[str, list] | None = None,
) -> dict:
    """单只候选深判（含失败隔离），返回一条结果 dict。"""
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
        return {
            "ticker": cand["ticker"],
            "name": cand["name"],
            "recommend": judgement["recommend"],
            "reasons": judgement.get("reasons", []),
            "criteria_hits": judgement.get("criteria_hits", []),
            "confidence": judgement.get("confidence"),
            "snapshot": _snapshot_fields(cand),
            "status": "ok",
            "error": None,
        }
    except ValueError as e:
        logger.warning("深判失败 %s: %s", cand["ticker"], e)
        return _failed_judgement(cand, str(e))
    except Exception as e:  # noqa: BLE001 — 网络超时等传输故障同样只隔离单只
        # 部分 httpx 超时的 str(e) 为空，带上类型名否则报告里只有 "LLM 调用异常: "
        detail = str(e).strip() or repr(e)
        logger.warning("深判异常 %s: %s", cand["ticker"], detail)
        return _failed_judgement(cand, f"LLM 调用异常({type(e).__name__}): {detail}")

