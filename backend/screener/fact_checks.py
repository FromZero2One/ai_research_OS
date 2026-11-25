"""事实检查 — 确定性规则替代 LLM 判断（审计意见/诉讼/现金覆盖）。

事实类标准不应交给 LLM：检索命中关键词即可判定，财务数字直接计算。
检索失败一律吞掉按 not_found（保守：缺证据不等于通过）。
"""

from __future__ import annotations

import asyncio

from core.logging import logger

# 事实检查轻量检索参数：top_k=3、无并发、单次/检查
_FACT_TOP_K = 3

_CHECK_QUERIES = {
    "audit_opinion": "审计意见 审计报告 无保留意见 保留意见",
    "litigation": "诉讼 重大违规 行政处罚 立案",
}

# 诉讼/处罚命中关键词（年报里出现即视为存在风险事项）
_LITIGATION_KEYWORDS = ("重大诉讼", "行政处罚", "立案调查", "监管处罚", "违规担保")

_CHECK_LABELS = {
    "audit_opinion": "审计意见",
    "litigation": "诉讼/处罚",
    "cash_coverage": "现金覆盖",
}


def _not_found(check: str, detail: str) -> dict:
    return {
        "check": check,
        "result": "not_found",
        "evidence": "",
        "citation": None,
        "detail": detail,
        "criterion": _CHECK_LABELS.get(check, check),
        "hit": False,
    }


async def _search_snippets(knowledge, query: str, company_id: str) -> list[str]:
    """单次检索（失败由调用方吞掉）。"""
    results = await knowledge.search(query, top_k=_FACT_TOP_K, company_id=company_id)
    return [getattr(r, "content", "") or str(r) for r in results if getattr(r, "content", "")]


async def _check_audit_opinion(knowledge, company_id: str) -> dict:
    """审计意见：命中「无保留意见」→ pass；命中「保留意见」（非无保留）→ fail；
    零命中 → not_found。
    """
    try:
        snippets = await _search_snippets(knowledge, _CHECK_QUERIES["audit_opinion"], company_id)
    except Exception as e:  # noqa: BLE001 — 检索故障不阻塞事实检查
        logger.warning("审计意见检索失败: %s", e)
        return _not_found("audit_opinion", "知识库检索失败")
    if not snippets:
        return _not_found("audit_opinion", "年报中未检索到审计意见段落")
    for i, text in enumerate(snippets, 1):
        if "无保留意见" in text:
            return {
                "check": "audit_opinion",
                "result": "pass",
                "evidence": text[:200],
                "citation": f"[{i}]",
                "detail": "年报披露无保留意见",
                "criterion": "审计意见",
                "hit": True,
            }
    for i, text in enumerate(snippets, 1):
        if "保留意见" in text:
            return {
                "check": "audit_opinion",
                "result": "fail",
                "evidence": text[:200],
                "citation": f"[{i}]",
                "detail": "年报披露保留意见",
                "criterion": "审计意见",
                "hit": False,
            }
    return _not_found("audit_opinion", "审计意见段落未含结论性表述")


async def _check_litigation(knowledge, company_id: str) -> dict:
    """诉讼/处罚：命中关键词即 fail；零命中 → not_found（缺信息不等于无风险）。"""
    try:
        snippets = await _search_snippets(knowledge, _CHECK_QUERIES["litigation"], company_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("诉讼检索失败: %s", e)
        return _not_found("litigation", "知识库检索失败")
    if not snippets:
        return _not_found("litigation", "年报中未检索到诉讼/处罚事项")
    for i, text in enumerate(snippets, 1):
        for kw in _LITIGATION_KEYWORDS:
            if kw in text:
                return {
                    "check": "litigation",
                    "result": "fail",
                    "evidence": f"{kw}：{text[:150]}",
                    "citation": f"[{i}]",
                    "detail": f"年报提及「{kw}」",
                    "criterion": "诉讼/处罚",
                    "hit": False,
                }
    return _not_found("litigation", "检索片段未含诉讼/处罚关键词")


def _check_cash_coverage_sync(check: dict, financials: dict) -> dict:
    """现金覆盖：财务数字直接计算，阈值取 check.threshold（缺数据 → not_found）。"""
    metric = check.get("metric") or "cash_ratio"
    threshold = float(check.get("threshold") or 1.0)
    value = financials.get(metric)
    try:
        fv = float(value)
    except (TypeError, ValueError):
        return _not_found("cash_coverage", f"缺少指标 {metric}，无法计算")
    label = check.get("label") or "现金覆盖"
    op = ">=" if fv >= threshold else "<"
    result = "pass" if fv >= threshold else "fail"
    return {
        "check": "cash_coverage",
        "result": result,
        "evidence": "",
        "citation": None,
        "detail": f"{label} {fv:.2f} {op} 阈值 {threshold:.2f}",
        "criterion": _CHECK_LABELS["cash_coverage"],
        "hit": result == "pass",
    }


async def run_fact_checks(
    checks: list[dict],
    knowledge,
    company_id: str | None,
    financials: dict,
) -> list[dict]:
    """执行事实检查清单，返回顺序同输入。

    每项 {check, result: pass|fail|not_found, evidence, citation, detail}。
    附带 criterion/hit 冗余字段以兼容 criteria_hits 下游消费（报告/导出/证据守卫）。
    knowledge 或 company_id 缺失 → 全部 not_found（不做跨公司检索）。
    """
    results: list[dict] = []
    tasks: dict[int, asyncio.Task] = {}
    for idx, check in enumerate(checks):
        name = check.get("check")
        if name == "cash_coverage":
            results.append(_check_cash_coverage_sync(check, financials or {}))
        elif name in ("audit_opinion", "litigation") and knowledge is not None and company_id:
            fn = _check_audit_opinion if name == "audit_opinion" else _check_litigation
            tasks[idx] = asyncio.ensure_future(fn(knowledge, company_id))
        else:
            reason = "无知识库或公司档案，跳过检索"
            results.append(_not_found(name or "unknown", reason))

    if tasks:
        done = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for (idx, _), res in zip(tasks.items(), done):
            if isinstance(res, Exception):  # noqa: BLE001
                logger.warning("事实检查异常 %s: %s", checks[idx].get("check"), res)
                res = _not_found(checks[idx].get("check") or "unknown", "检索异常")
            results.insert(idx, res)
    return results


def apply_fact_check_verdict(judgement: dict, fact_results: list[dict]) -> dict:
    """verdict 合成（纯函数）：任一 fail → reject；否则任一 not_found → insufficient；
    全 pass → 维持 LLM 结论。优先级 reject > insufficient > LLM。
    """
    fails = [r for r in fact_results if r.get("result") == "fail"]
    missing = [r for r in fact_results if r.get("result") == "not_found"]
    if fails:
        labels = "、".join(str(r.get("check")) for r in fails)
        return {
            **judgement,
            "recommend": False,
            "verdict": "reject",
            "reasons": [f"事实检查未通过：{labels}", *(judgement.get("reasons") or [])],
        }
    if missing:
        labels = "、".join(str(r.get("check")) for r in missing)
        return {
            **judgement,
            "recommend": False,
            "verdict": "insufficient",
            "reasons": [f"事实检查数据不足：{labels}", *(judgement.get("reasons") or [])],
        }
    return judgement
