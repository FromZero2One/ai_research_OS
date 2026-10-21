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


def build_report(
    run: dict,
    judgements: list[dict],
    criteria_text: str,
    excluded_missing_data: list[dict],
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
    lines.append("")
    lines.append("## 推荐列表")
    lines.append("")
    if not recommended:
        lines.append("本次无推荐 — 初筛候选均未通过定性判断。")
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
            for reason in j.get("reasons") or []:
                lines.append(f"- {reason}")
            lines.append("")

    # ── 标准吻合度说明：逐条对照标准原文 ──
    lines.append("## 标准吻合度说明")
    lines.append("")
    ok_judgements = recommended + rejected
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
