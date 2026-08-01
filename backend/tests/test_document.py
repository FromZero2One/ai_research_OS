"""Tests for Document Center — CRUD, upload pipeline.

Async tests (upload → chunk → embed → index) use the async_client fixture
which provides an ASGI transport + async event loop for Qdrant gRPC calls.
"""

from __future__ import annotations

from io import BytesIO

import httpx
import pytest
from fastapi.testclient import TestClient

from document.chunker import chunk_text


class TestChunker:
    """Chunker correctness — full coverage, no data loss, no infinite loop."""

    def test_short_text_single_chunk(self):
        assert chunk_text("hello world") == ["hello world"]

    def test_exact_size_single_chunk(self):
        text = "a" * 512
        assert chunk_text(text) == [text]

    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   \n\n  ") == []

    def test_long_text_covers_everything(self):
        """Regression: the old loop-safety check truncated long documents to
        the first ~2 chunks. Every character must appear in at least one chunk."""
        text = "".join(f"[{i:05d}]" for i in range(1500))
        chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)

        assert len(chunks) >= 3
        assert text.startswith(chunks[0])
        assert text.endswith(chunks[-1])
        joined = "".join(chunks)
        assert sum(len(c) for c in chunks) >= len(text)
        assert all(f"[{i:05d}]" in joined for i in range(1500))

    def test_long_chinese_text_covers_everything(self):
        text = "".join(chr(0x4E00 + i) for i in range(2000))
        chunks = chunk_text(text, chunk_size=512, chunk_overlap=64)

        assert len(chunks) >= 3
        assert text.startswith(chunks[0])
        assert text.endswith(chunks[-1])
        joined = "".join(chunks)
        assert set(joined) >= set(text)

    def test_degenerate_overlap_terminates(self):
        text = "".join(f"[{i:05d}]" for i in range(400))
        chunks = chunk_text(text, chunk_size=50, chunk_overlap=100)
        assert chunks
        joined = "".join(chunks)
        assert text.startswith(chunks[0])
        assert text.endswith(chunks[-1])
        assert all(f"[{i:05d}]" in joined for i in range(400))


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
        resp = client.delete("/api/v1/documents/00000000-0000-0000-0000-000000000000")
        assert resp.status_code == 404

    def test_search_by_doc_type(self, client: TestClient):
        resp = client.get("/api/v1/documents?doc_type=pdf")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0


class TestDocumentUploadAsync:
    """Async tests — full upload pipeline including Qdrant indexing."""

    @pytest.mark.asyncio
    async def test_upload_markdown(self, async_client: httpx.AsyncClient, test_session):
        content = (
            b"# Test Doc\n\nSimple test document content.\n\nWith multiple paragraphs for chunking."
        )
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.md", BytesIO(content), "text/markdown")},
            data={"title": "Test Doc", "doc_type": "markdown"},
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()
        assert data["title"] == "Test Doc"
        assert data["status"] == "indexing"
        assert data["is_indexed"] is False
        assert "id" in data

        # Upload is two-phase: index synchronously in the test (no worker).
        from core.container import create_container

        svc = create_container(test_session).document_service
        doc = await svc.index_document(data["id"])
        await test_session.commit()
        assert doc.is_indexed is True
        assert doc.chunk_count >= 1

        # Verify via API + status endpoint.
        resp2 = await async_client.get(f"/api/v1/documents/{data['id']}")
        assert resp2.json()["is_indexed"] is True
        status = await async_client.get(f"/api/v1/documents/{data['id']}/status")
        assert status.json()["is_indexed"] is True
        assert status.json()["step"] == "completed"

    @pytest.mark.asyncio
    async def test_upload_txt(self, async_client: httpx.AsyncClient, test_session):
        content = b"Plain text file content for testing."
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", BytesIO(content), "text/plain")},
            data={"title": "Plain Text", "doc_type": "text"},
        )
        assert resp.status_code == 202, resp.text
        from core.container import create_container

        svc = create_container(test_session).document_service
        doc = await svc.index_document(resp.json()["id"])
        await test_session.commit()
        assert doc.is_indexed is True

    @pytest.mark.asyncio
    async def test_upload_invalid_file_type(self, async_client: httpx.AsyncClient):
        """Should still accept unknown types — no strict validation yet."""
        content = b"some binary content"
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.xyz", BytesIO(content), "application/octet-stream")},
            data={"title": "Unknown", "doc_type": "other"},
        )
        # Accepted for background processing (parsed as plain text later).
        assert resp.status_code == 202, resp.text

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
        assert upload_resp.status_code == 202
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
        assert upload_resp.status_code == 202
        doc_id = upload_resp.json()["id"]

        # Delete
        del_resp = await async_client.delete(f"/api/v1/documents/{doc_id}")
        assert del_resp.status_code == 204

        # Verify 404
        get_resp = await async_client.get(f"/api/v1/documents/{doc_id}")
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_empty_file(self, async_client: httpx.AsyncClient, test_session):
        """Empty file should still be accepted and indexed (0 chunks)."""
        content = b""
        resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.md", BytesIO(content), "text/markdown")},
            data={"title": "Empty", "doc_type": "markdown"},
        )
        assert resp.status_code == 202, resp.text
        from core.container import create_container

        svc = create_container(test_session).document_service
        doc = await svc.index_document(resp.json()["id"])
        await test_session.commit()
        assert doc.is_indexed is True
        assert doc.chunk_count == 0
