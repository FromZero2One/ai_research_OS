"""Markdown 报告生成 — 推荐列表 + 标准吻合度说明 + 附表（纯函数）。

标准吻合度说明：对照标准原文的量化+定性条目逐条统计命中只数并给出代表例，
让用户能核对"它说符合标准"到底是不是真符合。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent


def report_path_for(run_id: str) -> Path:
    """报告文件路径：screener/reports/YYYY-MM-DD-<run_id前8>.md。"""
    day = datetime.now().strftime("%Y-%m-%d")
    return _MODULE_DIR / "reports" / f"{day}-{run_id[:8]}.md"


def _extract_criteria_items(criteria_text: str) -> list[str]:
    """从标准原文提取条目（列表行 / 小节标题下的行），用于吻合度逐条对照。"""
    items: list[str] = []
    for raw in criteria_text.splitlines():
        line = raw.strip().lstrip("-*· ").strip()
        if not line or line.startswith("#"):
            continue
        # 跳过"股票池：xxx"声明行（不是选股条件）
        if line.startswith("股票池"):
            continue
        items.append(line)
    return items


def _preset_mode(run: dict, judgements: list[dict]) -> bool:
    """union/intersection 预设模式判定：任一 judgement snapshot 带 presets 标注即启用。"""
    return any((j.get("snapshot") or {}).get("presets") for j in judgements)


def _preset_label(snapshot: dict) -> str:
    presets = snapshot.get("presets") or []
    label = " + ".join(presets)
    hits = snapshot.get("hits")
    if hits is not None and hits > 1:
        return f"{label}（{hits} 个）"
    return label


def build_report(
    run: dict,
    judgements: list[dict],
    criteria_text: str,
    excluded_missing_data: list[dict],
    financial_asof: str | None = None,
) -> str:
    """生成选股报告 Markdown。"""
    recommended = [j for j in judgements if j.get("status") == "ok" and j.get("recommend") is True]
    rejected = [j for j in judgements if j.get("status") == "ok" and j.get("recommend") is False]
    failed = [j for j in judgements if j.get("status") == "failed"]

    lines: list[str] = []
    lines.append(f"# 智能选股报告 {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append(
        f"- 候选数：{run.get('candidate_count', 0)} ｜ 推荐数：{len(recommended)} ｜ "
        f"深判失败：{len(failed)}"
    )
    if financial_asof:
        lines.append(f"- 财务数据截至：{financial_asof}")
    lines.append("")
    lines.append("## 推荐列表")
    lines.append("")
    preset_mode = _preset_mode(run, judgements)
    if not recommended:
        lines.append("本次无推荐 — 初筛候选均未通过定性判断。")
    elif preset_mode:
        lines.append("| 代码 | 名称 | 现价 | 总市值 | 置信度 | 命中预设 |")
        lines.append("|---|---|---|---|---|---|")
        for j in recommended:
            snap = j.get("snapshot") or {}
            lines.append(
                f"| {j['ticker']} | {j['name']} | {snap.get('price', '-')} | "
                f"{snap.get('market_cap', '-')} | {j.get('confidence', '-')} | {_preset_label(snap)} |"
            )
        lines.append("")
    else:
        lines.append("| 代码 | 名称 | 现价 | 总市值 | 置信度 |")
        lines.append("|---|---|---|---|---|")
        for j in recommended:
            snap = j.get("snapshot") or {}
            lines.append(
                f"| {j['ticker']} | {j['name']} | {snap.get('price', '-')} | "
                f"{snap.get('market_cap', '-')} | {j.get('confidence', '-')} |"
            )
        lines.append("")
        for j in recommended:
            lines.append(f"### {j['name']}（{j['ticker']}）")
            lines.append("")
            snap = j.get("snapshot") or {}
            if preset_mode and snap.get("presets"):
                lines.append(f"- 命中：{_preset_label(snap)}")
            for reason in j.get("reasons") or []:
                lines.append(f"- {reason}")
            lines.append("")

    # ── 标准吻合度说明：逐条对照标准原文 ──
    lines.append("## 标准吻合度说明")
    lines.append("")
    ok_judgements = recommended + rejected
    if preset_mode:
        # 预设模式的 criteria_text 是组合标签/投资逻辑，不是逐条标准；
        # 直接按深判返回的 criteria_hits 统计，避免文本匹配落空。
        order: list[str] = []
        stats: dict[str, dict] = {}
        for j in ok_judgements:
            for h in j.get("criteria_hits") or []:
                criterion = str(h.get("criterion", "")).strip()
                if not criterion:
                    continue
                if criterion not in stats:
                    order.append(criterion)
                    stats[criterion] = {"hits": 0, "misses": 0, "sample": None}
                if h.get("hit"):
                    stats[criterion]["hits"] += 1
                    if stats[criterion]["sample"] is None:
                        stats[criterion]["sample"] = (j["name"], h.get("evidence") or "见理由")
                else:
                    stats[criterion]["misses"] += 1
        if not order:
            lines.append("- 本次深判未返回标准命中明细")
        for criterion in order:
            s = stats[criterion]
            if s["hits"]:
                name, evidence = s["sample"]
                lines.append(f"- **{criterion}**：命中 {s['hits']} 只（如 {name} — {evidence}）")
            elif s["misses"]:
                lines.append(f"- **{criterion}**：{s['misses']} 只候选未命中该条")
            else:
                lines.append(f"- **{criterion}**：本次候选无相关判断记录")
    else:
        for item in _extract_criteria_items(criteria_text):
            hits = [j for j in ok_judgements if any(
                h.get("hit") and item in str(h.get("criterion", "")) for h in (j.get("criteria_hits") or [])
            )]
            misses = [j for j in ok_judgements if any(
                not h.get("hit") and item in str(h.get("criterion", "")) for h in (j.get("criteria_hits") or [])
            )]
            if hits:
                sample = hits[0]
                evidence = next(
                    (h.get("evidence", "") for h in sample.get("criteria_hits") or [] if h.get("hit") and item in str(h.get("criterion", ""))),
                    "",
                )
                lines.append(
                    f"- **{item}**：命中 {len(hits)} 只（如 {sample['name']} — {evidence or '见理由'}）"
                )
            elif misses:
                lines.append(f"- **{item}**：{len(misses)} 只候选未命中该条")
            else:
                lines.append(f"- **{item}**：本次候选无相关判断记录")
    lines.append("")

    lines.append("## 附：候选但未推荐")
    lines.append("")
    if not rejected:
        lines.append("无")
    else:
        for j in rejected:
            reason = "；".join((j.get("reasons") or [])[:2]) or "未通过定性判断"
            lines.append(f"- {j['name']}（{j['ticker']}）：{reason}")
    lines.append("")

    if failed:
        lines.append("## 附：深判失败")
        lines.append("")
        for j in failed:
            lines.append(f"- {j['name']}（{j['ticker']}）：{j.get('error', '未知原因')}")
        lines.append("")

    lines.append("## 附：因数据缺失被排除")
    lines.append("")
    if not excluded_missing_data:
        lines.append("无")
    else:
        for c in excluded_missing_data:
            missing = "、".join(c.get("missing") or [])
            lines.append(f"- {c.get('name', '')}（{c['ticker']}）：缺 {missing}")
    lines.append("")
    return "\n".join(lines)
