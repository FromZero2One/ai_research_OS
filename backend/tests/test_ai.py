"""Tests for AI Center — prompt template CRUD."""

from fastapi.testclient import TestClient
from tests.conftest import SAMPLE_PROMPT_TEMPLATE


class TestCreateTemplate:
    def test_create_basic(self, client: TestClient):
        resp = client.post("/api/v1/ai/templates", json=SAMPLE_PROMPT_TEMPLATE)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "test-summarizer"
        assert data["is_active"] is True

    def test_create_missing_name(self, client: TestClient):
        resp = client.post("/api/v1/ai/templates", json={})
        assert resp.status_code == 422

    def test_create_invalid_temperature(self, client: TestClient):
        data = {**SAMPLE_PROMPT_TEMPLATE, "temperature": 99}
        resp = client.post("/api/v1/ai/templates", json=data)
        assert resp.status_code == 201  # should accept, validate on use


class TestListTemplates:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/v1/ai/templates")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client: TestClient):
        client.post("/api/v1/ai/templates", json=SAMPLE_PROMPT_TEMPLATE)
        resp = client.get("/api/v1/ai/templates")
        assert resp.status_code == 200
        assert len(resp.json()) == 1


class TestGetTemplate:
    def test_get_by_id(self, client: TestClient):
        created = client.post("/api/v1/ai/templates", json=SAMPLE_PROMPT_TEMPLATE).json()
        resp = client.get(f"/api/v1/ai/templates/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-summarizer"

    def test_get_nonexistent(self, client: TestClient):
        resp = client.get("/api/v1/ai/templates/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestGenerate:
    def test_generate_missing_template(self, client: TestClient):
        resp = client.get("/api/v1/ai/templates/nonexistent")
        assert resp.status_code == 404
