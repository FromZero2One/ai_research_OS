"""组合构建单测 — 权重、单票/行业上限、现金保留。"""

from __future__ import annotations

import pytest

from screener.portfolio import construct_portfolio


def _c(ticker: str, industry: str = "银行", score: float = 1.0, confidence: float = 0.9) -> dict:
    return {
        "ticker": ticker, "name": ticker, "industry": industry,
        "score": score, "confidence": confidence, "price": 10.0,
    }


class TestConstructPortfolio:
    def test_equal_weights(self):
        result = construct_portfolio(
            [_c("A"), _c("B", "电子"), _c("C", "医药"), _c("D", "通信")],
            capital=100_000,
            max_weight=1.0,
            max_industry_weight=1.0,
        )
        assert len(result["holdings"]) == 4
        assert all(h["weight"] == pytest.approx(0.25) for h in result["holdings"])
        assert result["invested"] == pytest.approx(100_000)
        assert result["cash"] == pytest.approx(0)

    def test_single_stock_cap_leaves_cash(self):
        result = construct_portfolio(
            [_c("A"), _c("B", "电子")],
            capital=100_000,
            max_weight=0.15,
            max_industry_weight=1.0,
        )
        assert all(h["weight"] == pytest.approx(0.15) for h in result["holdings"])
        assert result["cash_weight"] == pytest.approx(0.70)
        assert any("现金" in w for w in result["warnings"])

    def test_industry_cap(self):
        result = construct_portfolio(
            [_c("A"), _c("B"), _c("C"), _c("D", "电子")],
            capital=100_000,
            max_weight=1.0,
            max_industry_weight=0.5,
        )
        bank = [h for h in result["holdings"] if h["industry"] == "银行"]
        assert sum(h["weight"] for h in bank) == pytest.approx(0.5)
        assert result["cash_weight"] == pytest.approx(0.25)

    def test_score_weighting(self):
        result = construct_portfolio(
            [_c("A", score=1.0), _c("B", "电子", score=3.0)],
            capital=100,
            method="score",
            max_weight=1.0,
            max_industry_weight=1.0,
        )
        by = {h["ticker"]: h for h in result["holdings"]}
        assert by["A"]["weight"] == pytest.approx(0.25)
        assert by["B"]["weight"] == pytest.approx(0.75)

    def test_max_holdings(self):
        result = construct_portfolio(
            [_c(str(i), industry=f"行业{i}") for i in range(5)],
            max_holdings=2,
            max_weight=1.0,
            max_industry_weight=1.0,
        )
        assert len(result["holdings"]) == 2
        assert any("截断" in w for w in result["warnings"])

    def test_empty_candidates_all_cash(self):
        result = construct_portfolio([])
        assert result["cash"] == result["capital"]
        assert result["holdings"] == []

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            construct_portfolio([_c("A")], capital=0)
        with pytest.raises(ValueError):
            construct_portfolio([_c("A")], max_weight=0)
        with pytest.raises(ValueError):
            construct_portfolio([_c("A")], method="magic")
