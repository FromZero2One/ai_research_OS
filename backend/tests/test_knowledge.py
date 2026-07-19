"""Tests for Knowledge Center — RAG search endpoint.

Note: Full RAG search requires Qdrant with indexed documents. These tests
need async event loop and are skipped in the sync test suite.
"""

import pytest
from fastapi.testclient import TestClient


class TestKnowledgeSearch:
    @pytest.mark.skip(reason="Needs async event loop for Qdrant gRPC")
    def test_search_empty(self, client: TestClient):
        resp = client.get("/api/v1/knowledge/search?query=test&top_k=5")
        assert resp.status_code == 200

    @pytest.mark.skip(reason="Needs async event loop for Qdrant gRPC")
    def test_search_after_document_upload(self, client: TestClient):
        pass  # tested via uvicorn curl test
