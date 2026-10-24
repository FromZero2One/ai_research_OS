"""预设组合规则纯函数 — union/intersection/flatten 组装 + union 初筛（零 LLM）。

plan 接口的 `evaluate_quant_rules_by_preset(pool, presets, financials)` 首参
pool 无法产出候选（候选来自 spot 采集，股票池过滤由 service 完成），
故首参为 candidates — 已记入 ledger Ruling。
"""

from __future__ import annotations

from typing import Any

from screener.industry import candidate_matches_scope
from screener.screening import evaluate_quant_rules

_FINANCIAL_SCOPES = {"financial", "bank", "insurance"}


def _sector_scope(presets: list[Any]) -> str:
    """单行业预设保留原 scope；纯金融组合 → financial；混合 → all；否则 industrial。"""
    tags = {getattr(p, "style_tag", None) for p in presets}
    if len(tags) == 1:
        tag = next(iter(tags))
        if tag in _FINANCIAL_SCOPES:
            return tag
    if tags and tags <= _FINANCIAL_SCOPES:
        return "financial"
    if tags & _FINANCIAL_SCOPES:
        return "all"
    return "industrial"


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
                # union 深判 criteria_hits 标注来源预设（spec 组合语义节）
                label = f"[{preset.name}] {q}" if combine == "union" else q
                qualitative.append(label)

    return {
        "stock_pool": {"type": pool},
        "quant_rules": quant_rules,
        "qualitative_criteria": qualitative,
        "candidate_limit": 50,
        "combine": combine,
        "preset_names": [p.name for p in presets],
        "sector_scope": _sector_scope(presets),
    }


def evaluate_quant_rules_by_preset(
    candidates: list[dict],
    presets: list[Any],
    financials_by_ticker: dict[str, list],
    collect_excluded: list[dict] | None = None,
) -> dict[str, dict]:
    """union 初筛：每个预设独立跑 evaluate_quant_rules，通过者合并去重。

    返回 {ticker: {"hits": 命中预设数, "presets": [预设名...], "score": 得分均值}}。
    全部预设都不命中的候选不出现。

    collect_excluded 非空时，把「没有任何预设命中、且至少被一个预设因缺数据
    排除」的候选合并写入（同票 missing 取并集），供报告展示数据缺口。
    至少命中一个预设的票不算被排除。
    """
    result: dict[str, dict] = {}
    excluded_map: dict[str, dict] = {}
    for preset in presets:
        # 金融/银行/保险预设只看对应行业；其它预设排除金融股（口径不可比）
        scope = getattr(preset, "style_tag", None) or "industrial"
        if scope not in _FINANCIAL_SCOPES:
            scope = "industrial"
        applicable = [c for c in candidates if candidate_matches_scope(c, scope)]
        passed, excluded = evaluate_quant_rules(
            applicable, preset.quant_rules, financials_by_ticker
        )
        for cand in passed:
            entry = result.setdefault(
                cand["ticker"],
                {
                    "ticker": cand["ticker"], "name": cand.get("name"),
                    "hits": 0, "presets": [], "scores": [],
                },
            )
            entry["hits"] += 1
            entry["presets"].append(preset.name)
            entry["scores"].append(cand.get("score", 0.0))
        for cand in excluded:
            entry = excluded_map.setdefault(
                cand["ticker"],
                {"ticker": cand["ticker"], "name": cand.get("name"),
                 "missing": set(), "presets": []},
            )
            entry["missing"].update(cand.get("missing") or [])
            if preset.name not in entry["presets"]:
                entry["presets"].append(preset.name)

    # 收敛为最终形状：score = 各预设得分均值（票数排名在 service 按 hits 排）
    for entry in result.values():
        scores = entry.pop("scores")
        entry["score"] = sum(scores) / len(scores) if scores else 0.0

    if collect_excluded is not None:
        for ticker, entry in excluded_map.items():
            if ticker in result:
                continue
            collect_excluded.append(
                {
                    "ticker": ticker,
                    "name": entry["name"],
                    "missing": sorted(entry["missing"]),
                    "presets": entry["presets"],
                }
            )
    return result


def evaluate_near_misses_by_preset(
    candidates: list[dict],
    presets: list[Any],
    financials_by_ticker: dict[str, list],
    exclude: set[str] | None = None,
    limit: int = 10,
) -> list[dict]:
    """union 模式近似命中：对每个预设单独找“只差一条规则”的票并去重。

    exclude 用于剔除已进入候选池的票；同一票命中多个预设的近似项时
    保留第一个预设的失败规则。结果按市值降序截断。
    """
    from screener.screening import evaluate_near_misses

    exclude = exclude or set()
    merged: dict[str, dict] = {}
    for preset in presets:
        scope = getattr(preset, "style_tag", None) or "industrial"
        if scope not in _FINANCIAL_SCOPES:
            scope = "industrial"
        applicable = [c for c in candidates if candidate_matches_scope(c, scope)]
        for item in evaluate_near_misses(
            applicable, preset.quant_rules, financials_by_ticker, limit=len(applicable)
        ):
            if item["ticker"] in exclude or item["ticker"] in merged:
                continue
            merged[item["ticker"]] = {**item, "preset": preset.name}
    ranked = sorted(
        merged.values(), key=lambda c: c.get("market_cap") or 0.0, reverse=True
    )
    return ranked[:limit]
