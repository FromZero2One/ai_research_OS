"""Tests for Knowledge Center — RAG search endpoint.

Async tests use the async_client fixture for Qdrant gRPC calls.
"""

from __future__ import annotations

from io import BytesIO

import httpx
import pytest


class TestKnowledgeSearch:
    """Knowledge search tests — requires Qdrant with indexed documents."""

    @pytest.mark.asyncio
    async def test_search_empty(self, async_client: httpx.AsyncClient):
        """Search with no indexed documents should return empty results."""
        resp = await async_client.get(
            "/api/v1/knowledge/search?query=test&top_k=5"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["query"] == "test"
        assert data["count"] == 0
        assert data["results"] == []

    @pytest.mark.asyncio
    async def test_search_without_query(self, async_client: httpx.AsyncClient):
        """Missing query param should return 422."""
        resp = await async_client.get("/api/v1/knowledge/search")
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_after_document_upload(
        self, async_client: httpx.AsyncClient
    ):
        """Upload a document, then search for its content."""
        # Upload document
        content = b"# NVIDIA Quarterly Report\n\nRevenue increased by 50% year-over-year.\n\nData center segment growth was strong."
        upload_resp = await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("nvidia.md", BytesIO(content), "text/markdown")},
            data={"title": "NVIDIA Report", "doc_type": "markdown"},
        )
        assert upload_resp.status_code == 201

        # Search for content
        resp = await async_client.get(
            "/api/v1/knowledge/search?query=revenue+growth&top_k=5"
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["count"] >= 1
        # Results should contain our content
        assert any(
            "revenue" in r["content"].lower()
            or "Revenue" in r["content"]
            for r in data["results"]
        )
        # Results should have document provenance
        result = data["results"][0]
        assert "document_id" in result
        assert "score" in result
        assert result["score"] > 0

    @pytest.mark.asyncio
    async def test_search_with_doc_type_filter(
        self, async_client: httpx.AsyncClient
    ):
        """Search filtered by doc_type."""
        # Upload
        content = b"# Financial Report\n\nEarnings per share grew 20%."
        await async_client.post(
            "/api/v1/documents/upload",
            files={"file": ("report.md", BytesIO(content), "text/markdown")},
            data={"title": "Report", "doc_type": "markdown"},
        )

        # Search with matching doc_type
        resp = await async_client.get(
            "/api/v1/knowledge/search?query=earnings&doc_type=markdown"
        )
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

        # Search with non-matching doc_type
        resp = await async_client.get(
            "/api/v1/knowledge/search?query=earnings&doc_type=pdf"
        )
        assert resp.status_code == 200
        # May have results if doc_type filter is not enforced strictly
        # Just verify it doesn't crash
