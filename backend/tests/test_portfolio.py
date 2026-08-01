"""Tests for Portfolio Center — watched companies, holdings, journal."""

from fastapi.testclient import TestClient

SAMPLE_HOLDING = {"ticker": "AAPL", "shares": 100, "avg_cost_basis": 150.0, "sector": "Technology"}
SAMPLE_JOURNAL = {
    "entry_type": "idea",
    "ticker": "NVDA",
    "title": "NVDA looks strong",
    "content": "NVIDIA has strong momentum in AI chips. Consider buying on dips.",
}


class TestWatchedCompanies:
    """Watchlist merged into Company — watched == is_active."""

    def test_company_active_by_default(self, client: TestClient):
        client.post("/api/v1/companies", json={"ticker": "WATCH1", "name": "Watch One"})
        resp = client.get("/api/v1/companies?is_active=true")
        assert resp.status_code == 200
        assert any(c["ticker"] == "WATCH1" for c in resp.json()["items"])

    def test_unwatch_and_rewatch_company(self, client: TestClient):
        created = client.post(
            "/api/v1/companies", json={"ticker": "WATCH2", "name": "Watch Two"}
        ).json()
        cid = created["id"]

        resp = client.patch(f"/api/v1/companies/{cid}", json={"is_active": False})
        assert resp.json()["is_active"] is False
        resp = client.get("/api/v1/companies?is_active=true")
        assert all(c["ticker"] != "WATCH2" for c in resp.json()["items"])

        client.patch(f"/api/v1/companies/{cid}", json={"is_active": True})
        resp = client.get("/api/v1/companies?is_active=true")
        assert any(c["ticker"] == "WATCH2" for c in resp.json()["items"])

    def test_dashboard_watchlist_sources_active_companies(self, client: TestClient):
        client.post(
            "/api/v1/companies",
            json={"ticker": "WATCH3", "name": "Watch Three", "priority": 2},
        )
        resp = client.get("/api/v1/dashboard")
        wl = resp.json()["watchlist"]
        assert wl and wl[0]["watchlist_name"] == "自选"
        assert any(i["ticker"] == "WATCH3" for i in wl[0]["items"])


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
        resp = client.patch(
            f"/api/v1/portfolio/holdings/{created['id']}",
            json={"is_active": False},
        )
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
