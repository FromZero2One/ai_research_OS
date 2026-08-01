"""Tests for AI Center — prompt template CRUD."""

from fastapi.testclient import TestClient

from ai.service import apply_variables
from tests.conftest import SAMPLE_PROMPT_TEMPLATE


class TestApplyVariables:
    """Safe {placeholder} substitution — no str.format crash on literal braces."""

    def test_substitutes_known_keys(self):
        assert apply_variables("Hello {name}!", {"name": "World"}) == "Hello World!"

    def test_unknown_placeholder_left_intact(self):
        assert apply_variables("Hi {name}", {"other": "x"}) == "Hi {name}"

    def test_literal_braces_do_not_crash(self):
        # str.format would raise on this — e.g. JSON examples in templates.
        assert apply_variables('{"a": 1}', {"a": "x"}) == '{"a": 1}'

    def test_empty_variables_returns_original(self):
        assert apply_variables("{name} {unused}", {}) == "{name} {unused}"


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
