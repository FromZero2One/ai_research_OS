"""回测报告渲染单测。"""

from __future__ import annotations

from screener.backtest_report import build_backtest_report


def _result() -> dict:
    return {
        "start": "2021-01-01",
        "end": "2024-12-31",
        "summary": {
            "total_return": 0.5,
            "bench_total_return": 0.1,
            "cagr": 0.12,
            "bench_cagr": 0.03,
            "excess_cagr": 0.09,
            "max_drawdown": -0.2,
            "annual_volatility": 0.18,
            "sharpe": 0.7,
            "sortino": 1.1,
            "calmar": 0.6,
            "win_rate": 0.75,
            "periods_count": 8,
            "split_sample": {
                "first_half": {
                    "periods_count": 4, "cagr": 0.2, "bench_cagr": 0.05,
                    "excess_cagr": 0.15, "max_drawdown": -0.1, "win_rate": 0.75,
                },
                "second_half": {
                    "periods_count": 4, "cagr": 0.05, "bench_cagr": 0.05,
                    "excess_cagr": 0.0, "max_drawdown": -0.2, "win_rate": 0.5,
                },
                "consistent_excess": False,
                "disclaimer": "对半切分仅作稳健性观察。",
            },
            "yearly": [],
        },
        "disclaimers": ["模拟结果不构成投资建议"],
    }


def test_report_contains_split_sample():
    report = build_backtest_report("run1", "核心资产", _result())
    assert "分段稳健性" in report
    assert "前半" in report and "后半" in report
    assert "+15.00%" in report
    assert "超额并非两段都为正" in report
    assert "对半切分仅作稳健性观察" in report
    assert "模拟结果不构成投资建议" in report


def test_report_skips_split_when_absent():
    result = _result()
    del result["summary"]["split_sample"]
    report = build_backtest_report("run1", "核心资产", result)
    assert "分段稳健性" not in report
