"""阶段5：财报多周期比对（YoY / QoQ / 同业对比）。

两层数据来源、一条铁律：
- YoY/QoQ：基于证据 structured_facts 中的**已核实数字**做确定性算术
  （相邻年度/季度），不是 LLM 推算；输出显式标注【计算得出】。
- 同业对比：基于 market.financial_metrics 表（标准枚举指标），
  取同 industry 公司的最新共同报告期，与本司对比中位数。

纯函数 + 独立查询，均可单测；任何环节缺数据都返回 None（静默降级）。
"""

from __future__ import annotations

import re
import statistics
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.logging import logger

# ── 报告期解析 ───────────────────────────────────────────────────────

_RE_ANNUAL = re.compile(r"(\d{4})\s*年?(?:报|年度|全年)?$")
_RE_QUARTER = re.compile(r"(\d{4})[Qq]\s*([1-4])$")
_RE_QUARTER_CN = re.compile(r"(\d{4})\s*年?(?:第\s*([一二三四1-4])\s*季?度?|([一二三四])季?度?)")


def parse_period(period: str | None) -> tuple[int, str, int] | None:
    """解析报告期字符串 → (year, type, quarter)。

    type ∈ {"annual", "q1".."q4", "semi"}；无法解析返回 None。
    例子：2024年报→(2024,"annual",0)；2025Q1→(2025,"q1",1)；2024中报→(2024,"semi",0)。
    """
    if not period or not isinstance(period, str):
        return None
    p = period.strip()

    if m := _RE_QUARTER.search(p):
        return int(m.group(1)), f"q{m.group(2)}", int(m.group(2))

    if m := _RE_QUARTER_CN.search(p):
        q = m.group(2) or m.group(3)
        if q:
            qn = {"一": 1, "二": 2, "三": 3, "四": 4}.get(q) or int(q)
            return int(m.group(1)), f"q{qn}", qn

    if "半年" in p or "中报" in p:
        if m := re.search(r"(\d{4})", p):
            return int(m.group(1)), "semi", 0
        return None

    if m := _RE_ANNUAL.search(p):
        return int(m.group(1)), "annual", 0
    return None


def _period_sort_key(pt: tuple[int, str, int]) -> tuple:
    year, typ, q = pt
    order = {"q1": 1, "q2": 2, "semi": 2, "q3": 3, "q4": 4, "annual": 4}
    return (year, order.get(typ, 0))


# ── YoY / QoQ（基于 structured_facts） ───────────────────────────────


def _collect_facts(evidences) -> list[dict]:
    """收集所有证据的结构化财务事实，附 evidence_id 便于溯源。"""
    facts: list[dict] = []
    for ev in evidences or []:
        sf = ev.structured_facts or {}
        if sf.get("not_mentioned"):
            continue
        for f in sf.get("facts") or []:
            if isinstance(f, dict) and f.get("metric_name") and f.get("value") is not None:
                facts.append({**f, "_evidence_id": str(getattr(ev, "id", ""))})
    return facts


def _pct_change(cur: float, prev: float) -> str:
    """计算百分比变化；基期为 0 或符号异常时返回说明文字（不做跨符号推算）。"""
    if prev == 0:
        return "基期为0，无法计算"
    if prev < 0 < cur or (prev > 0 > cur):
        return "基期与本期符号相反，不做跨盈亏推算"
    return f"{(cur - prev) / abs(prev) * 100:+.1f}%"


def _fmt_value(f: dict) -> str:
    return f"{f.get('value')}{f.get('unit') or ''}"


def compare_facts_periods(facts: list[dict]) -> list[str]:
    """对同指标跨期数字做 YoY/QoQ 计算，返回可读行（已按指标分组）。

    匹配规则：
    - YoY：annual 与相同季度（隔年）、semi 隔年；
    - QoQ：仅季度，相邻报告期（跨年如 2025Q1 vs 2024Q4 也算）。
    同名指标单位不一致（如 亿元 vs 万元）时跳过，避免错算。
    """
    # (metric, unit) -> {parsed_tuple(year, type, q): value}
    series: dict[tuple[str, str], dict[tuple[int, str, int], float]] = {}
    for f in facts:
        try:
            value = float(f["value"])
        except (TypeError, ValueError):
            continue
        pt = parse_period(f.get("period"))
        if not pt:
            continue
        unit = f.get("unit") or ""
        key = (str(f["metric_name"]), str(unit))
        series.setdefault(key, {})[pt] = value

    lines: list[str] = []
    seen_pairs: set[tuple] = set()
    for (metric, unit), points in series.items():
        sorted_pts = sorted(points.items(), key=lambda kv: _period_sort_key(kv[0]))
        for pos, ((y1, t1, _q1), v1) in enumerate(sorted_pts):
            # QoQ：仅季度类型且排序位置相邻（跨年如 2025Q1 vs 2024Q4 也成立）
            if pos > 0 and t1.startswith("q") and sorted_pts[pos - 1][0][1].startswith("q"):
                (y0, t0, _q0), v0 = sorted_pts[pos - 1]
                pair = ("qoq", metric, y0, t0, y1, t1)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    lines.append(
                        f"- {metric}（{unit}）QoQ：{_label(y0, t0)} → {_label(y1, t1)}："
                        f"{_fmt_value({'value': v0, 'unit': unit})}"
                        f" → {_fmt_value({'value': v1, 'unit': unit})}，"
                        f"变化 {_pct_change(v1, v0)}"
                    )
            # YoY：上一年同类型
            prev_key = (y1 - 1, t1, _q1)
            if prev_key in points:
                pair = ("yoy", metric, y1 - 1, t1, y1, t1)
                if pair not in seen_pairs:
                    seen_pairs.add(pair)
                    v0 = points[prev_key]
                    lines.append(
                        f"- {metric}（{unit}）YoY：{_label(y1 - 1, t1)} → {_label(y1, t1)}："
                        f"{_fmt_value({'value': v0, 'unit': unit})}"
                        f" → {_fmt_value({'value': v1, 'unit': unit})}，"
                        f"变化 {_pct_change(v1, v0)}"
                    )
    return lines


_CN_Q = {1: "Q1", 2: "Q2", 3: "Q3", 4: "Q4"}


def _label(year: int, typ: str) -> str:
    if typ.startswith("q"):
        return f"{year}{_CN_Q.get(int(typ[1]), typ)}"
    return f"{year}年报" if typ == "annual" else f"{year}半年报"


def build_period_comparison_block(evidences) -> str | None:
    """从证据 structured_facts 生成多周期比对区块（YoY/QoQ）；无可用数据返回 None。"""
    facts = _collect_facts(evidences)
    if not facts:
        return None
    lines = compare_facts_periods(facts)
    if not lines:
        return None
    return (
        "## Multi-period Comparison（YoY/QoQ）\n"
        "以下增长/变化率由已核实事实中的相邻报告期数字计算得出（非原文表述，非 LLM 推算），"
        "引用时请注明为计算值：\n" + "\n".join(lines)
    )


# ── 同业对比（基于 market.financial_metrics） ────────────────────────

_PEER_LIMIT = 5  # 最多取 5 家同业，控制上下文长度

_METRIC_CN = {
    "revenue": "营业收入",
    "net_income": "净利润",
    "gross_profit": "毛利润",
    "roe": "ROE",
    "roa": "ROA",
    "eps": "每股收益",
    "debt_to_equity": "资产负债率",
    "free_cash_flow": "自由现金流",
}


def build_peer_comparison_lines(
    subject_ticker: str,
    subject_metrics: dict[str, float],
    peer_metrics: dict[str, dict[str, list[float]]],
) -> list[str]:
    """同业对比纯函数：subject 指标值 vs 各同业中位数。

    subject_metrics: {metric_name: value}
    peer_metrics: {metric_name: {ticker: [各期值]}}（调用方已筛到最新共同期）
    """
    lines: list[str] = []
    for metric, my_value in sorted(subject_metrics.items()):
        peer_vals = [
            vals[-1]
            for t, vals in peer_metrics.get(metric, {}).items()
            if vals and vals[-1] is not None
        ]
        if len(peer_vals) < 2:
            continue
        med = statistics.median(peer_vals)
        if med == 0:
            continue
        rel = (my_value - med) / abs(med) * 100
        pos = "高于" if rel > 0 else ("低于" if rel < 0 else "持平于")
        cn = _METRIC_CN.get(metric, metric)
        lines.append(
            f"- {cn}：本司 {my_value:g}，同业中位 {med:g}"
            f"（n={len(peer_vals)}），{pos}同业 {abs(rel):.1f}%"
        )
    return lines


async def build_peer_comparison_block(
    db: AsyncSession, company_id: uuid.UUID | None
) -> str | None:
    """从财务指标库生成同业对比区块；公司缺行业/同业/指标时返回 None。"""
    if not company_id:
        return None

    from company.models import Company
    from market.models import FinancialMetric

    company = (
        await db.execute(select(Company).where(Company.id == company_id))
    ).scalar_one_or_none()
    if not company or not company.industry or not company.ticker:
        return None

    peers = (
        (
            await db.execute(
                select(Company)
                .where(
                    Company.industry == company.industry,
                    Company.id != company.id,
                    Company.ticker.isnot(None),
                )
                .limit(_PEER_LIMIT)
            )
        )
        .scalars()
        .all()
    )
    if not peers:
        return None

    tickers = [company.ticker, *(p.ticker for p in peers if p.ticker)]
    metrics = (
        (
            await db.execute(
                select(FinancialMetric)
                .where(
                    FinancialMetric.ticker.in_(tickers),
                    FinancialMetric.metric_value.isnot(None),
                )
                .order_by(
                    FinancialMetric.fiscal_year.desc(),
                    FinancialMetric.fiscal_period.desc(),
                )
            )
        )
        .scalars()
        .all()
    )
    if not metrics:
        return None

    # 指标 × ticker → 按期排序的值序列；取本司最新报告期为对比基准
    by_metric_ticker: dict[tuple[str, str], list[tuple[tuple, float]]] = {}
    for m in metrics:
        if m.metric_value is None:
            continue
        key = (m.metric_name, m.ticker)
        by_metric_ticker.setdefault(key, []).append(
            ((m.fiscal_year, m.fiscal_period), float(m.metric_value))
        )

    subject_periods = [
        k
        for (metric, ticker), vals in by_metric_ticker.items()
        if ticker == company.ticker
        for k, _ in vals
    ]
    if not subject_periods:
        return None
    latest = max(subject_periods)

    # 共同期筛选：仅保留本司与至少 2 家同业在该期都有值的指标
    subject_metrics: dict[str, float] = {}
    peer_metrics: dict[str, dict[str, list[float]]] = {}
    for (metric, ticker), vals in by_metric_ticker.items():
        val_map = {k: v for k, v in vals}
        if ticker == company.ticker:
            if latest in val_map:
                subject_metrics[metric] = val_map[latest]
        else:
            if latest in val_map:
                peer_metrics.setdefault(metric, {})[ticker] = [val_map[latest]]

    if not subject_metrics:
        return None

    lines = build_peer_comparison_lines(company.ticker, subject_metrics, peer_metrics)
    if not lines:
        return None

    year, period = latest
    logger.info("Peer comparison built for %s (%d lines)", company.ticker, len(lines))
    return (
        "## Peer Comparison（同业对比）\n"
        f"对比基准报告期：{year}{period}；同业（{company.industry}，"
        f"{len(peer_metrics.get('revenue', {})) or len(peers)} 家取中位数）。"
        "以下为数据库已入库指标的直接对比，非 LLM 推算：\n" + "\n".join(lines)
    )
