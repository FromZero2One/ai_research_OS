"""Tests for Research Center — full workflow: session → evidence → report → finalize."""

from fastapi.testclient import TestClient

import knowledge.service
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
        resp = client.post(
            "/api/v1/research/sessions",
            json={"title": "Minimal", "question": "Is this working?"},
        )
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
            f"/api/v1/research/sessions/{session['id']}/finalize",
            json={"thesis": "Strong BUY", "decision": "buy", "confidence": 0.85},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "completed"
        assert data["decision"] == "buy"
        assert data["confidence"] == 0.85

    def test_finalize_missing_thesis(self, client: TestClient):
        session = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.post(
            f"/api/v1/research/sessions/{session['id']}/finalize",
            json={"decision": "sell", "confidence": 0.7},
        )
        # thesis is required
        assert resp.status_code == 422

    def test_finalize_nonexistent(self, client: TestClient):
        resp = client.post(
            "/api/v1/research/sessions/00000000-0000-0000-0000-000000000000/finalize",
            json={"thesis": "test", "decision": "buy", "confidence": 0.5},
        )
        assert resp.status_code == 404


class TestDeleteSession:
    def test_delete_then_get_404(self, client: TestClient):
        created = client.post("/api/v1/research/sessions", json=SAMPLE_RESEARCH).json()
        resp = client.delete(f"/api/v1/research/sessions/{created['id']}")
        assert resp.status_code == 204
        resp = client.get(f"/api/v1/research/sessions/{created['id']}")
        assert resp.status_code == 404


class TestEvidenceInheritance:
    """跨会话证据继承：同公司已完成会话的证据带入新会话，标 inherited。"""

    def _create_company(self, client: TestClient) -> dict:
        resp = client.post(
            "/api/v1/companies",
            json={"ticker": "600519", "name": "贵州茅台"},
        )
        assert resp.status_code in (200, 201, 409), resp.text
        return resp.json()

    def _completed_session_with_evidence(
        self, client: TestClient, company_id: str, question: str, n: int
    ) -> dict:
        s = client.post(
            "/api/v1/research/sessions",
            json={"title": f"S-{question[:8]}", "question": question, "company_id": company_id},
        ).json()
        for i in range(n):
            client.post(
                f"/api/v1/research/sessions/{s['id']}/evidences",
                json={
                    "source_type": "document",
                    "source_id": f"{s['id']}-{i}",
                    "source_title": f"历史证据 {i}",
                    "content": f"历史已完成会话的证据内容 {i}：" + question,
                    "evidence_type": "supporting",
                },
            )
        client.patch(f"/api/v1/research/sessions/{s['id']}", json={"status": "completed"})
        return s

    @staticmethod
    def _mock_search_empty(monkeypatch):
        async def _search(self, query, **kwargs):
            return []

        monkeypatch.setattr(knowledge.service.KnowledgeService, "search", _search)

    def _new_session(self, client: TestClient, company_id: str) -> dict:
        return client.post(
            "/api/v1/research/sessions",
            json={"title": "新会话", "question": "茅台的投资价值如何？", "company_id": company_id},
        ).json()

    def test_inherit_from_completed_session(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        src = self._completed_session_with_evidence(
            client, company["id"], "茅台护城河深度分析？", 3
        )
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.status_code == 200, resp.text
        assert resp.json()["inherited_added"] == 3

        evidences = client.get(f"/api/v1/research/sessions/{new_s['id']}/evidences").json()
        inherited = [e for e in evidences if e["inherited_from_session_id"] == src["id"]]
        assert len(inherited) == 3

    def test_inherit_idempotent(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        self._completed_session_with_evidence(client, company["id"], "茅台的盈利能力分析？", 2)
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 0

    def test_draft_session_not_inherited(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        # 历史会话保持 draft（不设 completed）
        draft = client.post(
            "/api/v1/research/sessions",
            json={"title": "未完成", "question": "茅台的主要风险分析？",
                  "company_id": company["id"]},
        ).json()
        client.post(
            f"/api/v1/research/sessions/{draft['id']}/evidences",
            json={
                "source_type": "document",
                "source_id": "draft-1",
                "content": "未完成会话的证据内容",
                "evidence_type": "neutral",
            },
        )
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 0

    def test_dedup_against_existing(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        src = self._completed_session_with_evidence(
            client, company["id"], "茅台的估值水平分析？", 1
        )
        new_s = self._new_session(client, company["id"])
        # 手动加入与历史证据完全相同 (source_type, source_id, content) 的证据
        evidences = client.get(f"/api/v1/research/sessions/{src['id']}/evidences").json()
        same = evidences[0]
        client.post(
            f"/api/v1/research/sessions/{new_s['id']}/evidences",
            json={
                "source_type": same["source_type"],
                "source_id": same["source_id"],
                "content": same["content"],
                "evidence_type": "neutral",
            },
        )
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 0

    def test_limit_ten_newest_first(self, client: TestClient, monkeypatch):
        company = self._create_company(client)
        old = self._completed_session_with_evidence(
            client, company["id"], "老会话主题的研究问题", 6
        )
        new = self._completed_session_with_evidence(
            client, company["id"], "新会话主题的研究问题", 6
        )
        new_s = self._new_session(client, company["id"])
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.json()["inherited_added"] == 10

        evidences = client.get(f"/api/v1/research/sessions/{new_s['id']}/evidences").json()
        inherited_srcs = {
            e["inherited_from_session_id"] for e in evidences if e["inherited_from_session_id"]
        }
        # 新会话（updated_at 更晚）优先：12 条候选取 10 条，新会话 6 条全带，老会话补 4 条
        assert new["id"] in inherited_srcs
        assert old["id"] in inherited_srcs

    def test_no_company_no_inherit(self, client: TestClient, monkeypatch):
        # 无公司会话 + 存在已完成会话（未挂公司）也不继承
        src = client.post(
            "/api/v1/research/sessions",
            json={"title": "无公司会话", "question": "一个通用的研究问题？"},
        ).json()
        client.post(
            f"/api/v1/research/sessions/{src['id']}/evidences",
            json={
                "source_type": "document",
                "source_id": "nc-1",
                "content": "无公司会话的证据内容",
                "evidence_type": "neutral",
            },
        )
        client.patch(f"/api/v1/research/sessions/{src['id']}", json={"status": "completed"})

        new_s = client.post(
            "/api/v1/research/sessions",
            json={"title": "新无公司会话", "question": "另一个通用的研究问题"},
        ).json()
        self._mock_search_empty(monkeypatch)

        resp = client.post(f"/api/v1/research/sessions/{new_s['id']}/auto-gather")
        assert resp.status_code == 200
        assert resp.json()["inherited_added"] == 0
