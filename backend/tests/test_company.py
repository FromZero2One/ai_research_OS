"""Tests for Company Center — CRUD, search, tags."""

from fastapi.testclient import TestClient

from tests.conftest import SAMPLE_COMPANY


class TestCreateCompany:
    def test_create_basic(self, client: TestClient):
        resp = client.post("/api/v1/companies", json=SAMPLE_COMPANY)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["ticker"] == "TEST"
        assert data["name"] == "Test Corp"
        assert data["is_active"] is True
        assert "id" in data
        assert len(data["tags"]) == 2

    def test_create_duplicate_ticker(self, client: TestClient):
        client.post("/api/v1/companies", json=SAMPLE_COMPANY)
        resp = client.post("/api/v1/companies", json=SAMPLE_COMPANY)
        assert resp.status_code == 409
        assert "error" in resp.json()

    def test_create_ticker_uppercased(self, client: TestClient):
        data = {**SAMPLE_COMPANY, "ticker": "test_lower"}
        resp = client.post("/api/v1/companies", json=data)
        assert resp.status_code == 201, resp.text
        assert resp.json()["ticker"] == "TEST_LOWER"

    def test_create_missing_required(self, client: TestClient):
        resp = client.post("/api/v1/companies", json={})
        assert resp.status_code == 422

    def test_create_without_tags(self, client: TestClient):
        data = {k: v for k, v in SAMPLE_COMPANY.items() if k != "tags"}
        resp = client.post("/api/v1/companies", json=data)
        assert resp.status_code == 201, resp.text
        assert resp.json()["tags"] == []


class TestGetCompany:
    def test_get_by_id(self, client: TestClient):
        created = client.post("/api/v1/companies", json=SAMPLE_COMPANY).json()
        resp = client.get(f"/api/v1/companies/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["ticker"] == "TEST"

    def test_get_nonexistent(self, client: TestClient):
        resp = client.get(
            "/api/v1/companies/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_get_invalid_uuid(self, client: TestClient):
        resp = client.get("/api/v1/companies/not-a-uuid")
        assert resp.status_code == 422


class TestListCompanies:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/v1/companies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_list_with_data(self, client: TestClient):
        client.post("/api/v1/companies", json=SAMPLE_COMPANY)
        resp = client.get("/api/v1/companies")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_search_by_query(self, client: TestClient):
        client.post("/api/v1/companies", json=SAMPLE_COMPANY)
        resp = client.get("/api/v1/companies?query=Test")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 1

    def test_search_no_match(self, client: TestClient):
        resp = client.get("/api/v1/companies?query=ZZZ_MISSING")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestUpdateCompany:
    def test_update_name(self, client: TestClient):
        created = client.post("/api/v1/companies", json=SAMPLE_COMPANY).json()
        resp = client.patch(
            f"/api/v1/companies/{created['id']}",
            json={"name": "Updated Corp"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["name"] == "Updated Corp"
        # ticker should remain unchanged
        assert resp.json()["ticker"] == "TEST"

    def test_update_tags(self, client: TestClient):
        created = client.post("/api/v1/companies", json=SAMPLE_COMPANY).json()
        resp = client.patch(
            f"/api/v1/companies/{created['id']}",
            json={"tags": ["ai", "semiconductor"]},
        )
        assert resp.status_code == 200, resp.text
        tag_names = [t["tag"] for t in resp.json()["tags"]]
        assert "ai" in tag_names
        assert "tech" not in tag_names

    def test_update_nonexistent(self, client: TestClient):
        resp = client.patch(
            "/api/v1/companies/00000000-0000-0000-0000-000000000000",
            json={"name": "Ghost"},
        )
        assert resp.status_code == 404


class TestDeleteCompany:
    def test_delete_then_get_404(self, client: TestClient):
        created = client.post("/api/v1/companies", json=SAMPLE_COMPANY).json()
        resp = client.delete(f"/api/v1/companies/{created['id']}")
        assert resp.status_code == 204
        # Verify it's gone
        resp = client.get(f"/api/v1/companies/{created['id']}")
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client: TestClient):
        resp = client.delete(
            "/api/v1/companies/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404
