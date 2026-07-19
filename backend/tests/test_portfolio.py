"""Tests for Portfolio Center — watchlists, holdings, journal."""

from fastapi.testclient import TestClient


SAMPLE_WATCHLIST = {"name": "AI Stocks", "description": "Top AI companies to watch"}
SAMPLE_HOLDING = {"ticker": "AAPL", "shares": 100, "avg_cost_basis": 150.0, "sector": "Technology"}
SAMPLE_JOURNAL = {
    "entry_type": "idea",
    "ticker": "NVDA",
    "title": "NVDA looks strong",
    "content": "NVIDIA has strong momentum in AI chips. Consider buying on dips.",
}


class TestWatchlist:
    def test_create_watchlist(self, client: TestClient):
        resp = client.post("/api/v1/portfolio/watchlists", json=SAMPLE_WATCHLIST)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "AI Stocks"
        assert "id" in data

    def test_list_watchlists_empty(self, client: TestClient):
        resp = client.get("/api/v1/portfolio/watchlists")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_watchlists_with_data(self, client: TestClient):
        client.post("/api/v1/portfolio/watchlists", json=SAMPLE_WATCHLIST)
        resp = client.get("/api/v1/portfolio/watchlists")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_add_item_to_watchlist(self, client: TestClient):
        wl = client.post("/api/v1/portfolio/watchlists", json=SAMPLE_WATCHLIST).json()
        resp = client.post(
            f"/api/v1/portfolio/watchlists/{wl['id']}/items",
            json={"ticker": "NVDA", "notes": "AI leader", "reason": "Strong growth"},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["ticker"] == "NVDA"

    def test_get_watchlist_with_items(self, client: TestClient):
        wl = client.post("/api/v1/portfolio/watchlists", json=SAMPLE_WATCHLIST).json()
        client.post(f"/api/v1/portfolio/watchlists/{wl['id']}/items", json={"ticker": "NVDA"})
        resp = client.get(f"/api/v1/portfolio/watchlists/{wl['id']}")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 1

    def test_delete_watchlist(self, client: TestClient):
        wl = client.post("/api/v1/portfolio/watchlists", json=SAMPLE_WATCHLIST).json()
        resp = client.delete(f"/api/v1/portfolio/watchlists/{wl['id']}")
        assert resp.status_code == 204
        resp = client.get(f"/api/v1/portfolio/watchlists/{wl['id']}")
        assert resp.status_code == 404


class TestHolding:
    def test_add_holding(self, client: TestClient):
        resp = client.post("/api/v1/portfolio/holdings", json=SAMPLE_HOLDING)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert data["is_active"] is True

    def test_list_holdings_empty(self, client: TestClient):
        resp = client.get("/api/v1/portfolio/holdings")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_holdings_with_data(self, client: TestClient):
        client.post("/api/v1/portfolio/holdings", json=SAMPLE_HOLDING)
        resp = client.get("/api/v1/portfolio/holdings")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_close_holding(self, client: TestClient):
        created = client.post("/api/v1/portfolio/holdings", json=SAMPLE_HOLDING).json()
        resp = client.patch(f"/api/v1/portfolio/holdings/{created['id']}", json={"is_active": False})
        assert resp.status_code == 200, resp.text
        assert resp.json()["is_active"] is False


class TestJournal:
    def test_create_entry(self, client: TestClient):
        resp = client.post("/api/v1/portfolio/journal", json=SAMPLE_JOURNAL)
        assert resp.status_code == 201, resp.text
        assert resp.json()["title"] == "NVDA looks strong"

    def test_list_journal_empty(self, client: TestClient):
        resp = client.get("/api/v1/portfolio/journal")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_journal_with_data(self, client: TestClient):
        client.post("/api/v1/portfolio/journal", json=SAMPLE_JOURNAL)
        resp = client.get("/api/v1/portfolio/journal")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
