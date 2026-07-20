"""Tests for Document Center — CRUD, upload pipeline.

Async tests (upload → chunk → embed → index) use the async_client fixture
which provides an ASGI transport + async event loop for Qdrant gRPC calls.
"""

from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient


class TestDocumentCRUD:
    """Synchronous DB-only tests — no Qdrant needed."""

    def test_list_empty(self, client: TestClient):
        resp = client.get("/api/v1/documents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0
        assert data["items"] == []

    def test_get_nonexistent(self, client: TestClient):
        resp = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_delete_nonexistent(self, client: TestClient):
        resp = client.delete(
            "/api/v1/documents/00000000-0000-0000-0000-000000000000"
        )
        assert resp.status_code == 404

    def test_search_by_doc_type(self, client: TestClient):
        resp = client.get("/api/v1/documents?doc_type=pdf")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestDocumentUploadAsync:
    """Async tests — full upload pipeline including Qdrant indexing."""

    @pytest.mark.asyncio
    async def test_upload_markdown(self, async_client: httpx.AsyncClient):
        content = b"# Test Doc\n\nSimple test document content.\n\nWith multiple paragraphs for chunking."
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.md", BytesIO(content), "text/markdown")},
            data={"title": "Test Doc", "doc_type": "markdown"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["title"] == "Test Doc"
        assert data["is_indexed"] is True
        assert data["chunk_count"] >= 1
        assert "id" in data

    @pytest.mark.asyncio
    async def test_upload_txt(self, async_client: httpx.AsyncClient):
        content = b"Plain text file content for testing."
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", BytesIO(content), "text/plain")},
            data={"title": "Plain Text", "doc_type": "text"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["is_indexed"] is True

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(self, async_client: httpx.AsyncClient):
        """Should still accept unknown types — no strict validation yet."""
        content = b"some binary content"
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.xyz", BytesIO(content), "application/octet-stream")},
            data={"title": "Unknown", "doc_type": "other"},
        )
        # Should handle gracefully (parse as plain text)
        assert resp.status_code in (201, 400), resp.text

    @pytest.mark.asyncio
    async def test_get_document_after_upload(self, async_client: httpx.AsyncClient):
        """Upload then retrieve by ID."""
        # Upload
        content = b"# Get Test\n\nContent for get test."
        upload_resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("get_test.md", BytesIO(content), "text/markdown")},
            data={"title": "Get Test", "doc_type": "markdown"},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        # Get by ID
        resp = await async_client.get(f"/api/v1/documents/{doc_id}")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["id"] == doc_id
        assert data["title"] == "Get Test"

    @pytest.mark.asyncio
    async def test_delete_document_after_upload(self, async_client: httpx.AsyncClient):
        """Upload then delete then verify 404."""
        # Upload
        content = b"# Delete Test\n\nContent for delete test."
        upload_resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("delete_test.md", BytesIO(content), "text/markdown")},
            data={"title": "Delete Test", "doc_type": "markdown"},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["id"]

        # Delete
        del_resp = await async_client.delete(f"/api/v1/documents/{doc_id}")
        assert del_resp.status_code == 204

        # Verify 404
        get_resp = await async_client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_empty_file(self, async_client: httpx.AsyncClient):
        """Empty file should still be accepted and indexed (0 chunks)."""
        content = b""
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.md", BytesIO(content), "text/markdown")},
            data={"title": "Empty", "doc_type": "markdown"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["is_indexed"] is True
        assert data["chunk_count"] == 0
