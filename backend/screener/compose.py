"""预设组合规则纯函数 — union/intersection/flatten 组装 + union 初筛（零 LLM）。

plan 接口的 `evaluate_quant_rules_by_preset(pool, presets, financials)` 首参
pool 无法产出候选（候选来自 spot 采集，股票池过滤由 service 完成），
故首参为 candidates — 已记入 ledger Ruling。
"""

from __future__ import annotations

from typing import Any

from screener.screening import evaluate_quant_rules


def compose_rules(presets: list[Any], pool: str, combine: str) -> dict:
    """把 1-N 个预设组装成与 v1 rules 同形状的 dict。

    - flatten：quant_rules 拼接 AND，同 metric 冲突按传入顺序后者覆盖（保持首次出现位置）
    - intersection：quant_rules 全拼接（不去重），combine 标记
    - union：qualitative 去重拼接保持顺序（量化筛选走 evaluate_quant_rules_by_preset）
    pool 参数覆盖各预设的 suggested_pool。
    """
    if not presets:
        raise ValueError("至少选择一个预设")

    quant_rules: list[dict] = []
    seen_metrics: dict[str, int] = {}
    qualitative: list[str] = []
    seen_qual: set[str] = set()
    for preset in presets:
        for rule in preset.quant_rules:
            metric = rule["metric"]
            if combine == "flatten":
                if metric in seen_metrics:
                    # 后者覆盖前者：原位替换，保持确定性顺序
                    quant_rules[seen_metrics[metric]] = rule
                    continue
                seen_metrics[metric] = len(quant_rules)
            # intersection/union：全部保留（AND 拼接）
            quant_rules.append(rule)
        for q in preset.qualitative:
            if q not in seen_qual:
                seen_qual.add(q)
                qualitative.append(q)

    return {
        "stock_pool": {"type": pool},
        "quant_rules": quant_rules,
        "qualitative_criteria": qualitative,
        "candidate_limit": 50,
        "combine": combine,
        "preset_names": [p.name for p in presets],
    }


def evaluate_quant_rules_by_preset(
    candidates: list[dict],
    presets: list[Any],
    financials_by_ticker: dict[str, list],
) -> dict[str, dict]:
    """union 初筛：每个预设独立跑 evaluate_quant_rules，通过者合并去重。

    返回 {ticker: {"hits": 命中预设数, "presets": [预设名...], "score": 得分均值}}。
    全部预设都不命中的候选不出现。
    """
    result: dict[str, dict] = {}
    for preset in presets:
        passed, _excluded = evaluate_quant_rules(candidates, preset.quant_rules, financials_by_ticker)
        for cand in passed:
            entry = result.setdefault(
                cand["ticker"],
                {"ticker": cand["ticker"], "name": cand.get("name"), "hits": 0, "presets": [], "scores": []},
            )
            entry["hits"] += 1
            entry["presets"].append(preset.name)
            entry["scores"].append(cand.get("score", 0.0))

    # 收敛为最终形状：score = 各预设得分均值（票数排名在 service 按 hits 排）
    for entry in result.values():
        scores = entry.pop("scores")
        entry["score"] = sum(scores) / len(scores) if scores else 0.0
    return result
