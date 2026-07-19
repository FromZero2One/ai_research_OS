"""Tests for Market Center — price and financial data endpoints."""

from fastapi.testclient import TestClient


class TestMarketData:
    def test_get_prices_empty(self, client: TestClient):
        resp = client.get("/api/v1/market/prices/AAPL")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # Response shape: {"ticker": "AAPL", "prices": []}
        if isinstance(data, list):
            assert data == []  # old format
        else:
            assert "prices" in data
            assert data["prices"] == []

    def test_get_financials_empty(self, client: TestClient):
        resp = client.get("/api/v1/market/financials/AAPL")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        if isinstance(data, list):
            assert data == []
        else:
            assert "metrics" in data or "financials" in data or data == []
