"""回测报告渲染 — Markdown（汇总指标 + 逐年明细 + 免责声明）。"""

from __future__ import annotations


def build_backtest_report(run_id: str, preset_name: str, result: dict) -> str:
    """result JSON → Markdown。结构见 spec 2026-10-23。"""
    summary = result.get("summary", result)  # 兼容顶层/嵌套两种形状
    lines: list[str] = []
    lines.append(f"# 预设回测报告：{preset_name}（{result.get('start')} ~ {result.get('end')}）")
    lines.append("")
    lines.append("## 概览")
    lines.append("")
    lines.append(
        f"- 回测区间：{result.get('start')} ~ {result.get('end')} ｜ 调仓次数：{summary.get('periods_count', 0)}"
    )
    lines.append("")
    lines.append("## 汇总指标")
    lines.append("")
    lines.append(f"- 累计收益：{summary.get('total_return', 0):.2%}")
    lines.append(f"- 基准（沪深300）累计：{summary.get('bench_total_return', 0):.2%}")
    lines.append(f"- 年化收益（CAGR）：{summary.get('cagr', 0):.2%}")
    lines.append(f"- 基准年化：{summary.get('bench_cagr', 0):.2%}")
    lines.append(f"- 年化超额：{summary.get('excess_cagr', 0):+.2%}")
    lines.append(f"- 最大回撤：{summary.get('max_drawdown', 0):.2%}")
    lines.append(f"- 年化波动：{summary.get('annual_volatility', 0):.2%}")
    lines.append(f"- Sharpe：{summary.get('sharpe', 0):.2f}")
    lines.append(f"- Sortino：{summary.get('sortino', 0):.2f}")
    lines.append(f"- Calmar：{summary.get('calmar', 0):.2f}")
    lines.append(f"- 年度胜率（超额>0 占比）：{summary.get('win_rate', 0):.0%}")
    lines.append("")
    lines.append("## 逐年明细")
    lines.append("")
    for y in summary.get("yearly", []):
        lines.append(f"### {y['year']}（调仓日 {y.get('rebalance_date')}）")
        lines.append("")
        lines.append(
            f"- 期收益：{y['return']:.2%} ｜ 基准：{y['bench']:.2%} ｜ 超额：{y['excess']:+.2%}"
        )
        lines.append("")
        if y.get("holdings"):
            lines.append("| 代码 | 名称 | 买入价 | 卖出价 | 收益 | 停牌 |")
            lines.append("|---|---|---|---|---|---|")
            for h in y["holdings"]:
                buy = f"{h['buy']:.2f}" if h.get("buy") is not None else "-"
                sell = f"{h['sell']:.2f}" if h.get("sell") is not None else "-"
                lines.append(
                    f"| {h['ticker']} | {h.get('name', '-')} | {buy} | {sell} | "
                    f"{h['return']:.2%} | {'是' if h.get('suspended') else '否'} |"
                )
            lines.append("")
        else:
            lines.append("- 本期无入选股票")
            lines.append("")
    lines.append("## 数据说明与免责声明")
    lines.append("")
    for d in result.get("disclaimers", []):
        lines.append(f"- {d}")
    lines.append("")
    return "\n".join(lines)
