"""股票池过滤纯函数单测（不依赖数据库）。"""

from __future__ import annotations

from screener.pool import board_of, filter_pool


def _spot(*tickers: str) -> list[dict]:
    names = {"600519": "贵州茅台", "000001": "平安银行", "300750": "宁德时代", "688981": "中芯国际"}
    return [
        {"ticker": t, "name": names.get(t, t), "price": 10.0, "turnover": 1.5, "market_cap": 1e11}
        for t in tickers
    ]


def _item(ticker: str, name: str, price=10.0, turnover=1.5, market_cap=1e11) -> dict:
    return {
        "ticker": ticker, "name": name,
        "price": price, "turnover": turnover, "market_cap": market_cap,
    }


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


class TestPoolHygiene:
    def test_excludes_st_and_delisting(self):
        items = [
            _item("600001", "*ST测试"),
            _item("600002", "ST测试"),
            _item("600003", "退市测试"),
            _item("600519", "贵州茅台"),
        ]
        stats: dict[str, int] = {}
        out = filter_pool(items, {"type": "all"}, set(), excluded_out=stats)
        assert [c["ticker"] for c in out] == ["600519"]
        assert stats["st"] == 3

    def test_excludes_suspended_low_liquidity_and_small_cap(self):
        items = [
            _item("600001", "停牌股", price=None),
            _item("600002", "低换手", turnover=0.01),
            _item("600003", "小市值", market_cap=5e8),
            _item("600519", "贵州茅台"),
        ]
        stats: dict[str, int] = {}
        out = filter_pool(items, {"type": "all"}, set(), excluded_out=stats)
        assert [c["ticker"] for c in out] == ["600519"]
        assert stats["suspended"] == 1
        assert stats["low_liquidity"] == 1
        assert stats["small_cap"] == 1
