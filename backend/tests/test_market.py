"""Tests for Market Center — price, financials, search, info endpoints.

Note: Some tests depend on akshare MySQL having data for specific symbols.
      600519 (贵州茅台) and 000001 (平安银行) are expected to exist.
"""

from fastapi.testclient import TestClient


class TestMarketData:
    def test_get_prices_a_stock(self, client: TestClient):
        """A-stock prices come from MySQL adapter."""
        resp = client.get("/api/v1/market/prices/600519?limit=3")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "prices" in data
        assert len(data["prices"]) > 0
        assert "close" in data["prices"][0]

    def test_get_prices_us_stock(self, client: TestClient):
        """US stock prices return empty from PG (no data ingested)."""
        resp = client.get("/api/v1/market/prices/AAPL?limit=3")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["prices"] == []

    def test_get_financials(self, client: TestClient):
        resp = client.get("/api/v1/market/financials/000001?fiscal_year=2026")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["count"] > 0

    def test_search_by_name(self, client: TestClient):
        resp = client.get("/api/v1/market/search?query=茅台")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["count"] >= 1

    def test_search_by_symbol(self, client: TestClient):
        resp = client.get("/api/v1/market/search?query=600519")
        assert resp.status_code == 200, resp.text
        assert resp.json()["count"] >= 1

    def test_stock_info(self, client: TestClient):
        resp = client.get("/api/v1/market/info/600519")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["name"] is not None
        assert "valuation" in data

    def test_list_symbols(self, client: TestClient):
        resp = client.get("/api/v1/market/symbols?limit=5")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["count"] > 0
        assert len(data["symbols"]) > 0
