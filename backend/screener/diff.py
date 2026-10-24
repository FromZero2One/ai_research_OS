"""选股变化日报 — 对比两次同口径运行，只报变化（纯函数可单测）。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from screener.report import _fmt_money, _fmt_price

_MODULE_DIR = Path(__file__).resolve().parent


def diff_path_for(run_id: str) -> Path:
    day = datetime.now().strftime("%Y-%m-%d")
    return _MODULE_DIR / "reports" / f"{day}-diff-{run_id[:8]}.md"


def _is_recommended(judgement: dict) -> bool:
    return judgement.get("status") == "ok" and judgement.get("recommend") is True


def _by_ticker(judgements: list[dict]) -> dict[str, dict]:
    return {j["ticker"]: j for j in judgements if j.get("ticker")}


def compute_diff(current: list[dict], previous: list[dict]) -> dict:
    """返回新增/掉出的推荐与候选（候选列表排除已在新推荐中重复展示的票）。"""
    cur_all = _by_ticker(current)
    prev_all = _by_ticker(previous)
    cur_rec = {t: j for t, j in cur_all.items() if _is_recommended(j)}
    prev_rec = {t: j for t, j in prev_all.items() if _is_recommended(j)}

    new_rec = [cur_rec[t] for t in sorted(cur_rec) if t not in prev_rec]
    dropped_rec = [prev_rec[t] for t in sorted(prev_rec) if t not in cur_rec]
    new_cand = [
        cur_all[t] for t in sorted(cur_all)
        if t not in prev_all and t not in cur_rec
    ]
    dropped_cand = [
        prev_all[t] for t in sorted(prev_all)
        if t not in cur_all and t not in prev_rec
    ]
    return {
        "new_recommended": new_rec,
        "dropped_recommended": dropped_rec,
        "new_candidates": new_cand,
        "dropped_candidates": dropped_cand,
        "counts": {
            "new_recommended": len(new_rec),
            "dropped_recommended": len(dropped_rec),
            "new_candidates": len(new_cand),
            "dropped_candidates": len(dropped_cand),
        },
    }


def _fmt_ts(value) -> str:
    """DB/API 的 UTC 时间 → 本地时间文本。"""
    if value is None:
        return "-"
    try:
        if isinstance(value, str):
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value.astimezone().strftime("%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return str(value)


def _stock_row(j: dict) -> str:
    snap = j.get("snapshot") or {}
    return (
        f"| {j['ticker']} | {j.get('name') or '-'} | {snap.get('industry') or '-'} | "
        f"{_fmt_price(snap.get('price'))} | {_fmt_money(snap.get('market_cap'))} | "
        f"{j.get('confidence', '-')} |"
    )


def _append_stock_table(lines: list[str], title: str, rows: list[dict]) -> None:
    lines.append(f"## {title}")
    lines.append("")
    if not rows:
        lines.append("无")
    else:
        lines.append("| 代码 | 名称 | 行业 | 现价 | 总市值 | 置信度 |")
        lines.append("|---|---|---|---|---|---|")
        for j in rows:
            lines.append(_stock_row(j))
    lines.append("")


def build_diff_markdown(
    current_run: dict,
    previous_run: dict | None,
    diff: dict | None,
) -> str:
    lines = [
        f"# 智能选股变化日报 {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## 运行对比",
        "",
        f"- 当前运行：{current_run.get('id', '-')[:8]}（{_fmt_ts(current_run.get('created_at'))}）",
    ]
    if previous_run is None:
        lines.append("- 对比基线：无（首次运行）")
        lines.append("")
        lines.append("首次运行，暂无历史基线，下一轮开始可生成变化。")
        lines.append("")
        return "\n".join(lines)

    prev_id = previous_run.get("id", "-")[:8]
    prev_ts = _fmt_ts(previous_run.get("created_at"))
    lines.append(f"- 对比基线：{prev_id}（{prev_ts}）")
    lines.append(
        f"- 候选数：{previous_run.get('candidate_count', '-')} → "
        f"{current_run.get('candidate_count', '-')} ｜ 推荐数："
        f"{previous_run.get('result_count', '-')} → {current_run.get('result_count', '-')}"
    )
    lines.append("")

    counts = (diff or {}).get("counts", {})
    lines.append("## 变化概览")
    lines.append("")
    lines.append(
        f"- 新推荐 {counts.get('new_recommended', 0)} 只 ｜ "
        f"掉出推荐 {counts.get('dropped_recommended', 0)} 只"
    )
    lines.append(
        f"- 新进候选 {counts.get('new_candidates', 0)} 只 ｜ "
        f"移出候选 {counts.get('dropped_candidates', 0)} 只"
    )
    lines.append("")

    if not any(counts.values()):
        lines.append("本次无变化。")
        lines.append("")
        return "\n".join(lines)

    _append_stock_table(lines, "新推荐", (diff or {}).get("new_recommended") or [])
    _append_stock_table(lines, "掉出推荐", (diff or {}).get("dropped_recommended") or [])
    _append_stock_table(lines, "新进候选", (diff or {}).get("new_candidates") or [])
    _append_stock_table(lines, "移出候选", (diff or {}).get("dropped_candidates") or [])
    return "\n".join(lines)
