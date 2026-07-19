"""Tests for Document Center — upload, CRUD, and pipeline.

Note: The full upload→chunk→embed→index pipeline requires a running Qdrant
instance and async event loop. Tests that exercise the pipeline are marked
@pytest.mark.skip and should be run with the ASYNC test client.
"""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient


class TestDocumentCRUD:
    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.skip(reason="Needs async event loop for Qdrant gRPC")
    def test_upload_markdown(self, client: TestClient):
        content = b"# Test Doc\n\nSimple test document content."
        resp = client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.md", BytesIO(content), "text/markdown")},
            data={"title": "Test Document", "doc_type": "markdown"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["title"] == "Test Document"
        assert data["is_indexed"] is True
        assert data["chunk_count"] >= 1

    @pytest.mark.skip(reason="Needs async event loop for Qdrant gRPC")
    def test_get_document_by_id(self, client: TestClient):
        pass  # tested via uvicorn curl test

    @pytest.mark.skip(reason="Needs async event loop for Qdrant gRPC")
    def test_delete_document(self, client: TestClient):
        pass

    def test_get_nonexistent(self, client: TestClient):
        resp = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404
