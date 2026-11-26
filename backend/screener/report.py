"""Markdown 报告生成 — 推荐列表 + 标准吻合度说明 + 附表（纯函数）。

标准吻合度说明：对照标准原文的量化条目逐条统计命中只数并给出代表例，
让用户能核对"它说符合标准"到底是不是真符合。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from core.config import settings

_MODULE_DIR = Path(__file__).resolve().parent


def _fmt_price(value) -> str:
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-" if value is None else str(value)


def _fmt_money(value) -> str:
    """金额转亿/万，报告里不直接暴露原始浮点。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "-" if value is None else str(value)
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f} 亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.2f} 万"
    return f"{v:.2f}"


def _normalize_criterion_with_presets(text: str, preset_names: list[str]) -> str:
    """去掉 LLM 返回的预设前缀，合并「[深度价值] 现金充裕」与「深度价值 - 现金充裕」。"""
    s = str(text).strip()
    s = re.sub(r"^\[[^\]]+\]\s*", "", s)
    for name in sorted(preset_names, key=len, reverse=True):
        if s.startswith(name):
            rest = s[len(name):].lstrip(" -—：:")
            if rest:
                s = rest
                break
    return s.strip()


def _preset_names_for(run: dict, judgements: list[dict]) -> list[str]:
    names = list(run.get("preset_names") or [])
    if names:
        return names
    return sorted({
        name
        for j in judgements
        for name in ((j.get("snapshot") or {}).get("presets") or [])
    })


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


def _normalize_criterion(text: str) -> str:
    """标准化判定条目：去除首尾空格、剥离合并模式下的预设前缀（如 "[核心资产] "）、折叠内部空白。"""
    t = text.strip()
    # 剥离 "[预设名] " 前缀
    t = re.sub(r"^\[[^\]]+\]\s*", "", t)
    # 折叠连续空白
    t = re.sub(r"\s+", " ", t)
    return t


def _criterion_matches_item(criterion: str, item: str) -> bool:
    """判定条目是否命中标准条目：优先精确匹配（标准化后），失败则回退子串匹配。"""
    if _normalize_criterion(criterion) == _normalize_criterion(item):
        return True
    # 回退：原始子串匹配，保留对 LLM 措辞微小差异的兼容
    return item in criterion or criterion in item


def build_report(
    run: dict,
    judgements: list[dict],
    criteria_text: str,
    excluded_missing_data: list[dict],
    financial_asof: str | None = None,
    spot_taken_at: str | None = None,
    pool_stats: dict[str, int] | None = None,
    knowledge_docs: int | None = None,
    has_qualitative: bool = False,
    prev_recommendations: set[str] | None = None,
    prev_finished_at: str | None = None,
) -> str:
    """生成选股报告 Markdown。

    prev_recommendations（上一轮推荐 ticker 集合）非 None 时，
    报告尾部追加轮次对比：新增 / 移出 / 连续推荐。
    """
    recommended = [j for j in judgements if j.get("status") == "ok" and j.get("recommend") is True]
    insufficient = [
        j for j in judgements
        if j.get("status") == "ok"
        and j.get("recommend") is False
        and j.get("verdict") == "insufficient"
    ]
    rejected = [
        j for j in judgements
        if j.get("status") == "ok"
        and j.get("recommend") is False
        and j.get("verdict") != "insufficient"
    ]
    failed = [j for j in judgements if j.get("status") == "failed"]

    lines: list[str] = []
    lines.append(f"# 智能选股报告 {datetime.now().strftime('%Y-%m-%d')}")
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append(
        f"- 候选数：{run.get('candidate_count', 0)} ｜ 推荐数：{len(recommended)} ｜ "
        f"数据不足：{len(insufficient)} ｜ 深判失败：{len(failed)}"
    )
    if financial_asof:
        lines.append(f"- 财务数据截至：{financial_asof}")
    if spot_taken_at:
        lines.append(f"- 快照时间：{spot_taken_at}（新浪源，缓存命中时为缓存采集时间）")
    if has_qualitative and knowledge_docs == 0:
        lines.append(
            "- ⚠ 知识库为空：定性标准会稳定判为“数据不足”，"
            "请先在文档中心上传并索引年报/公告"
        )
    lines.append("")
    lines.append("## 推荐列表")
    lines.append("")
    preset_mode = _preset_mode(run, judgements)
    preset_names = _preset_names_for(run, judgements)
    if not recommended:
        lines.append("本次无推荐 — 初筛候选均未通过确定性判定。")
    elif preset_mode:
        lines.append("| 代码 | 名称 | 行业 | 现价 | 总市值 | 命中预设 |")
        lines.append("|---|---|---|---|---|---|")
        for j in recommended:
            snap = j.get("snapshot") or {}
            lines.append(
                f"| {j['ticker']} | {j['name']} | {snap.get('industry') or '-'} | "
                f"{_fmt_price(snap.get('price'))} | "
                f"{_fmt_money(snap.get('market_cap'))} | "
                f"{_preset_label(snap)} |"
            )
        lines.append("")
    else:
        lines.append("| 代码 | 名称 | 行业 | 现价 | 总市值 |")
        lines.append("|---|---|---|---|---|")
        for j in recommended:
            snap = j.get("snapshot") or {}
            lines.append(
                f"| {j['ticker']} | {j['name']} | {snap.get('industry') or '-'} | "
                f"{_fmt_price(snap.get('price'))} | "
                f"{_fmt_money(snap.get('market_cap'))} |"
            )
        lines.append("")

    # 推荐个股：三段固定结构（量化筛选 → 事实检查 → 不推荐/存疑原因）
    for j in recommended:
        lines.append(f"### {j['name']}（{j['ticker']}）")
        lines.append("")
        snap = j.get("snapshot") or {}
        # ── 1 量化筛选（数值 + 行业分位）──
        lines.append("**量化筛选**")
        lines.append("")
        if snap.get("industry"):
            lines.append(f"- 行业：{snap['industry']}")
        lines.append(
            f"- 现价 {_fmt_price(snap.get('price'))} ｜ 总市值 {_fmt_money(snap.get('market_cap'))}"
        )
        if snap.get("score") is not None:
            lines.append(f"- 初筛得分：{snap['score']}")
        percentiles = snap.get("industry_percentiles") or {}
        if percentiles:
            labels = {
                "roe": "ROE", "revenue_growth": "营收增长",
                "net_income_growth": "净利增长", "cfo_to_ni": "现金流/净利",
                "pe": "PE", "pb": "PB",
            }
            parts = [
                f"{labels.get(k, k)} {float(v) * 100:.0f}%"
                for k, v in percentiles.items()
                if v is not None
            ]
            if parts:
                lines.append("- 行业分位：" + "、".join(parts))
        if preset_mode and snap.get("presets"):
            lines.append(f"- 命中：{_preset_label(snap)}")

        hits = j.get("criteria_hits") or []
        fact_entries = [h for h in hits if isinstance(h, dict) and "check" in h and "result" in h]

        # ── 2 事实检查（确定性检查结果）──
        lines.append("")
        lines.append("**事实检查**")
        lines.append("")
        if not fact_entries:
            lines.append("- 无")
        else:
            _RESULT_LABELS = {"exempt": "不适用（已豁免）"}
            for f in fact_entries:
                cite = f"（{f['citation']}）" if f.get("citation") else ""
                detail = f" {f.get('detail') or ''}".rstrip()
                res_label = _RESULT_LABELS.get(f["result"], f["result"])
                lines.append(f"- {f.get('criterion') or f['check']}：{res_label}{cite}{detail}")
        for reason in j.get("reasons") or []:
            lines.append(f"- {reason}")

        # ── 3 不推荐/存疑原因（数据来源：事实检查 not_found 项 + 缺数据排除项）──
        lines.append("")
        lines.append("**不推荐/存疑原因**")
        lines.append("")
        doubts = [
            f"{f.get('criterion') or f['check']} 未检出（数据不足，非通过）"
            for f in fact_entries if f.get("result") == "not_found"
        ]
        for c in excluded_missing_data:
            if c.get("ticker") == j.get("ticker"):
                missing = "、".join(c.get("missing") or [])
                if missing:
                    doubts.append(f"量化指标缺数据：{missing}")
        if doubts:
            for d in doubts:
                lines.append(f"- {d}")
        else:
            lines.append("- 无")
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
                criterion = _normalize_criterion_with_presets(
                    str(h.get("criterion", "")), preset_names
                )
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
                h.get("hit") and _criterion_matches_item(str(h.get("criterion", "")), item) for h in (j.get("criteria_hits") or [])
            )]
            misses = [j for j in ok_judgements if any(
                not h.get("hit") and _criterion_matches_item(str(h.get("criterion", "")), item) for h in (j.get("criteria_hits") or [])
            )]
            if hits:
                sample = hits[0]
                evidence = next(
                    (h.get("evidence", "") for h in sample.get("criteria_hits") or [] if h.get("hit") and _criterion_matches_item(str(h.get("criterion", "")), item)),
                    "",
                )
                lines.append(
                    f"- **{item}**：命中 {len(hits)} 只"
                    f"（如 {sample['name']} — {evidence or '见理由'}）"
                )
            elif misses:
                lines.append(f"- **{item}**：{len(misses)} 只候选未命中该条")
            else:
                lines.append(f"- **{item}**：本次候选无相关判断记录")
    lines.append("")

    lines.append("## 附：未通过标准（未推荐）")
    lines.append("")
    if not rejected:
        lines.append("无")
    else:
        for j in rejected:
            reason = "；".join((j.get("reasons") or [])[:2]) or "未通过确定性判定"
            lines.append(f"- {j['name']}（{j['ticker']}）：{reason}")
    lines.append("")

    lines.append("## 附：数据不足（未推荐）")
    lines.append("")
    if not insufficient:
        lines.append("无")
    else:
        for j in insufficient:
            reason = "；".join((j.get("reasons") or [])[:2]) or "证据不足，无法判断"
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

    if pool_stats is not None:
        lines.append("## 附：股票池卫生过滤")
        lines.append("")
        stats = [
            ("ST/*ST/退市", pool_stats.get("st", 0)),
            ("停牌/无行情", pool_stats.get("suspended", 0)),
            (
                f"低流动性（换手率 < {settings.SCREENER_MIN_TURNOVER:g}%）",
                pool_stats.get("low_liquidity", 0),
            ),
            (
                f"小市值（< {settings.SCREENER_MIN_MARKET_CAP / 1e8:g} 亿）",
                pool_stats.get("small_cap", 0),
            ),
        ]
        nonzero = [(label, n) for label, n in stats if n]
        if not nonzero:
            lines.append("无（所有股票均通过卫生过滤）")
        else:
            for label, n in stats:
                lines.append(f"- {label}：{n} 只")
        lines.append("")

    if prev_recommendations is not None:
        now_tickers = {j["ticker"] for j in recommended if j.get("ticker")}
        added = sorted(now_tickers - prev_recommendations)
        removed = sorted(prev_recommendations - now_tickers)
        kept = sorted(now_tickers & prev_recommendations)
        prev_label = prev_finished_at or "上轮"
        lines.append(f"## 较上一轮（{prev_label}）")
        lines.append("")

        def _names(tickers: list[str]) -> str:
            name_of = {j.get("ticker"): j.get("name") or "" for j in judgements}
            return "、".join(f"{t} {name_of.get(t) or ''}".strip() for t in tickers) or "无"

        lines.append(f"- 新增 {len(added)} 只：{_names(added)}")
        lines.append(f"- 移出 {len(removed)} 只：{_names(removed)}")
        lines.append(f"- 连续推荐 {len(kept)} 只：{_names(kept)}")
        lines.append("")
    return "\n".join(lines)
