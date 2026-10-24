"""LLM 深判评测 — 标注用例、证据纪律检查与汇总（纯函数 + 单例执行）。"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from screener.judge import _is_doc_only, judge_one

DEFAULT_CASES_PATH = Path(__file__).resolve().parent / "eval" / "judge_cases.jsonl"


@dataclass
class EvalResult:
    case_id: str
    status: str
    recommend: bool | None
    confidence: float | None
    expected_recommend: bool | None
    recommend_match: bool | None
    violations: list[str]
    downgraded: int
    latency: float


class _SnippetKnowledge:
    def __init__(self, snippets: list[str]):
        self._snippets = snippets

    async def search(self, *args, **kwargs):
        return [SimpleNamespace(content=s) for s in self._snippets]


def load_cases(path: str | Path = DEFAULT_CASES_PATH) -> list[dict]:
    cases: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _violations(judgement: dict, snippets: list[str]) -> list[str]:
    violations: list[str] = []
    for hit in judgement.get("criteria_hits") or []:
        if not isinstance(hit, dict) or not hit.get("hit"):
            continue
        criterion = str(hit.get("criterion") or "")
        evidence = str(hit.get("evidence") or "")
        if not snippets:
            if _is_doc_only(criterion):
                violations.append(f"doc_only_without_snippets:{criterion}")
            elif not re.search(r"\d", evidence):
                violations.append(f"financial_hit_without_number:{criterion}")
        elif not re.search(r"\[\d+\]", evidence):
            violations.append(f"missing_citation:{criterion}")
    return violations


def score_case(case: dict, judgement: dict, latency: float) -> EvalResult:
    expected = case.get("expected") or {}
    expected_recommend = expected.get("recommend")
    recommend = judgement.get("recommend")
    snippets = case.get("snippets") or []
    violations = _violations(judgement, snippets)
    downgraded = sum(
        1
        for hit in judgement.get("criteria_hits") or []
        if "自动降级" in str((hit or {}).get("evidence") or "")
    )
    return EvalResult(
        case_id=case.get("id", ""),
        status="ok",
        recommend=recommend,
        confidence=judgement.get("confidence"),
        expected_recommend=expected_recommend,
        recommend_match=(
            None if expected_recommend is None else recommend == expected_recommend
        ),
        violations=violations,
        downgraded=downgraded,
        latency=latency,
    )


async def run_case(llm, case: dict) -> EvalResult:
    candidate = {
        "ticker": case["ticker"],
        "name": case.get("name", case["ticker"]),
        "industry": case.get("industry"),
        "sector": case.get("sector"),
        "price": case.get("price"),
        "turnover": case.get("turnover"),
        "market_cap": case.get("market_cap"),
        "score": case.get("score"),
    }
    started = time.monotonic()
    try:
        judgement = await judge_one(
            llm,
            candidate,
            case.get("criteria") or [],
            knowledge=(
                _SnippetKnowledge(case["snippets"]) if case.get("snippets") else None
            ),
            financials=case.get("financials") or {},
        )
    except Exception as e:  # noqa: BLE001 — 评测要记录失败而不是中断
        return EvalResult(
            case_id=case.get("id", ""),
            status="failed",
            recommend=None,
            confidence=None,
            expected_recommend=(case.get("expected") or {}).get("recommend"),
            recommend_match=False,
            violations=[f"exception:{type(e).__name__}:{e}"],
            downgraded=0,
            latency=time.monotonic() - started,
        )
    return score_case(case, judgement, time.monotonic() - started)


def summarize(results: list[EvalResult]) -> dict:
    checked = [r for r in results if r.recommend_match is not None]
    return {
        "cases": len(results),
        "json_valid": sum(1 for r in results if r.status == "ok"),
        "json_valid_rate": (
            sum(1 for r in results if r.status == "ok") / len(results) if results else 0.0
        ),
        "recommend_checked": len(checked),
        "recommend_match": sum(1 for r in checked if r.recommend_match),
        "recommend_match_rate": (
            sum(1 for r in checked if r.recommend_match) / len(checked) if checked else None
        ),
        "cases_with_violations": sum(1 for r in results if r.violations),
        "total_violations": sum(len(r.violations) for r in results),
        "downgraded_hits": sum(r.downgraded for r in results),
        "avg_latency_s": (
            sum(r.latency for r in results) / len(results) if results else 0.0
        ),
    }


def build_eval_markdown(model_name: str, results: list[EvalResult]) -> str:
    summary = summarize(results)
    lines = [
        "# LLM 深判评测报告",
        "",
        f"- 模型：{model_name}",
        f"- 用例数：{summary['cases']}",
        f"- JSON 合法率：{summary['json_valid_rate']:.1%}",
    ]
    if summary["recommend_match_rate"] is not None:
        lines.append(
            f"- 推荐判定匹配：{summary['recommend_match']}/{summary['recommend_checked']} "
            f"（{summary['recommend_match_rate']:.1%}）"
        )
    lines.append(
        f"- 证据纪律：{summary['cases_with_violations']} 个用例存在违规，"
        f"共 {summary['total_violations']} 条"
    )
    lines.append(f"- 自动降级命中：{summary['downgraded_hits']} 条")
    lines.append(f"- 平均耗时：{summary['avg_latency_s']:.2f}s")
    lines.append("")
    lines.append("| 用例 | 状态 | 推荐 | 期望 | 匹配 | 违规 | 降级 | 耗时 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for r in results:
        lines.append(
            f"| {r.case_id} | {r.status} | {r.recommend} | {r.expected_recommend} | "
            f"{r.recommend_match} | {'; '.join(r.violations) or '-'} | "
            f"{r.downgraded} | {r.latency:.1f}s |"
        )
    lines.append("")
    return "\n".join(lines)
