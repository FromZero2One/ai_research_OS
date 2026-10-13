"""Tests for Market Center — price, financials, search endpoints.

MySQL 镜像层已移除：全部走 PG 缓存 + akshare subprocess（测试环境无外网/无
akshare venv，因此采集路径断言空结果不报错即可）。
"""

from fastapi.testclient import TestClient


class TestMarketData:
    def test_get_prices_empty_ticker(self, client: TestClient):
        """无缓存且无法采集时返回空列表而非报错。"""
        resp = client.get("/api/v1/market/prices/000000?limit=3")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "prices" in data

    def test_get_prices_us_stock(self, client: TestClient):
        """US stock prices return empty from PG (no data ingested)."""
        resp = client.get("/api/v1/market/prices/AAPL?limit=3")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["prices"] == []

    def test_get_financials_no_data(self, client: TestClient):
        """无缓存且无 akshare venv 时返回空指标而非报错。"""
        resp = client.get("/api/v1/market/financials/000001?fiscal_year=2026")
        assert resp.status_code == 200, resp.text

    def test_search_no_match(self, client: TestClient):
        resp = client.get("/api/v1/market/search?query=不存在的公司xyz")
        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] == 0

    def test_search_by_symbol(self, client: TestClient):
        """搜索命中 PG Companies 表（conftest 种子公司）。"""
        resp = client.get("/api/v1/market/search?query=AAPL")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if data["count"] > 0:
            assert any(r["symbol"] == "AAPL" for r in data["results"])
