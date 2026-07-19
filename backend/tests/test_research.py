"""Tests for Research Center — full workflow: session → evidence → report → finalize."""

from fastapi.testclient import TestClient
from tests.conftest import SAMPLE_RESEARCH


SAMPLE_EVIDENCE = {
    "source_type": "article",
    "source_id": "test-001",
    "source_title": "Test Article",
    "content": "This is test evidence content for research.",
    "evidence_type": "supporting",
    "relevance_score": 0.85,
}

SAMPLE_REPORT = {
    "title": "Research Report v1",
    "content": "## Summary\nThis is the research report content.",
    "format_": "markdown",
}


class TestCreateSession:
    def test_create_basic(self, client: TestClient):
        resp = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["title"] == SAMPLE_RESEARCH["title"]
        assert data["status"] == "draft"
        assert "id" in data

    def test_create_minimal(self, client: TestClient):
        resp = client.post("/api/v1/research/sessions", json={"title": "Minimal", "question": "Is this working?"})
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "draft"

    def test_create_missing_title(self, client: TestClient):
        resp = client.post("/api/v1/research/sessions", json={"question": "?"})
        assert resp.status_code == 422

    def test_create_missing_question(self, client: TestClient):
        resp = client.post("/api/v1/research/sessions", json={"title": "No Q"})
        assert resp.status_code == 422


class TestListSessions:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/v1/research/sessions")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_with_data(self, client: TestClient):
        client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH)
        resp = client.get("/api/v1/research/sessions")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_filter_by_status(self, client: TestClient):
        client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH)
        resp = client.get("/api/v1/research/sessions?status=draft")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        resp = client.get("/api/v1/research/sessions?status=completed")
        assert len(resp.json()) == 0


class TestGetSession:
    def test_get_by_id(self, client: TestClient):
        created = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.get(f"/api/v1/research/sessions/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["title"] == SAMPLE_RESEARCH["title"]

    def test_get_nonexistent(self, client: TestClient):
        resp = client.get("/api/v1/research/sessions/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404


class TestUpdateSession:
    def test_update_status(self, client: TestClient):
        created = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.patch(
            f"/api/v1/research/sessions/{created['id']}",
            json={"status": "researching"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "researching"

    def test_update_nonexistent(self, client: TestClient):
        resp = client.patch(
            "/api/v1/research/sessions/00000000-0000-0000-0000-000000000000",
            json={"status": "completed"},
        )
        assert resp.status_code == 404


class TestEvidenceWorkflow:
    def test_add_evidence(self, client: TestClient):
        session = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.post(
            f"/api/v1/research/sessions/{session['id']}/evidences",
            json=SAMPLE_EVIDENCE,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["evidence_type"] == "supporting"
        assert data["source_title"] == "Test Article"

    def test_list_evidences(self, client: TestClient):
        session = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        client.post(f"/api/v1/research/sessions/{session['id']}/evidences", json=SAMPLE_EVIDENCE)
        resp = client.get(f"/api/v1/research/sessions/{session['id']}/evidences")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_add_evidence_auto_transitions_status(self, client: TestClient):
        """Adding evidence to a draft session should auto-transition to researching."""
        session = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        assert session["status"] == "draft"
        client.post(f"/api/v1/research/sessions/{session['id']}/evidences", json=SAMPLE_EVIDENCE)
        updated = client.get(f"/api/v1/research/sessions/{session['id']}").json()
        assert updated["status"] == "researching"


class TestFinalize:
    def test_finalize_session(self, client: TestClient):
        session = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.post(
            f"/api/v1/research/sessions/{session['id']}/finalize"
            "?thesis=Strong+BUY&decision=buy&confidence=0.85",
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "completed"
        assert data["decision"] == "buy"
        assert data["confidence"] == 0.85

    def test_finalize_missing_thesis(self, client: TestClient):
        session = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.post(
            f"/api/v1/research/sessions/{session['id']}/finalize"
            "?decision=sell&confidence=0.7",
        )
        # thesis is required
        assert resp.status_code == 422

    def test_finalize_nonexistent(self, client: TestClient):
        resp = client.post(
            "/api/v1/research/sessions/00000000-0000-0000-0000-000000000000/finalize"
            "?thesis=test&decision=buy&confidence=0.5",
        )
        assert resp.status_code == 404


class TestDeleteSession:
    def test_delete_then_get_404(self, client: TestClient):
        created = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.delete(f"/api/v1/research/sessions/{created['id']}")
        assert resp.status_code == 204
        resp = client.get(f"/api/v1/research/sessions/{created['id']}")
        assert resp.status_code == 404
