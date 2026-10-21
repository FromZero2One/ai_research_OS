"""股票池过滤纯函数单测（不依赖数据库）。"""

from __future__ import annotations

from screener.pool import board_of, filter_pool


def _spot(*tickers: str) -> list[dict]:
    names = {"600519": "贵州茅台", "000001": "平安银行", "300750": "宁德时代", "688981": "中芯国际"}
    return [
        {"ticker": t, "name": names.get(t, t), "price": 10.0, "turnover": 1.5, "market_cap": 100.0}
        for t in tickers
    ]


class TestBoardOf:
    def test_main(self):
        assert board_of("600519") == "main"
        assert board_of("000001") == "main"

    def test_chinext(self):
        assert board_of("300750") == "chinext"

    def test_star(self):
        assert board_of("688981") == "star"

    def test_non_a_stock(self):
        assert board_of("AAPL") is None
        assert board_of("") is None


class TestFilterPool:
    def test_all(self):
        out = filter_pool(_spot("600519", "300750", "688981", "AAPL"), {"type": "all", "tickers": []}, set())
        assert [c["ticker"] for c in out] == ["600519", "300750", "688981"]

    def test_main_only(self):
        out = filter_pool(_spot("600519", "300750"), {"type": "main", "tickers": []}, set())
        assert [c["ticker"] for c in out] == ["600519"]

    def test_chinext_only(self):
        out = filter_pool(_spot("600519", "300750"), {"type": "chinext", "tickers": []}, set())
        assert [c["ticker"] for c in out] == ["300750"]

    def test_star_only(self):
        out = filter_pool(_spot("600519", "688981"), {"type": "star", "tickers": []}, set())
        assert [c["ticker"] for c in out] == ["688981"]

    def test_watchlist_union(self):
        """watchlist 池 = 自选公司 ∪ 文档内列出 ticker。"""
        pool = {"type": "watchlist", "tickers": ["688981"]}
        out = filter_pool(_spot("600519", "688981", "300750"), pool, {"600519"})
        assert sorted(c["ticker"] for c in out) == ["600519", "688981"]
