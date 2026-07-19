"""Tests for core infrastructure — exceptions, security, config."""

from __future__ import annotations

from fastapi.testclient import TestClient

from core.config import settings
from core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    DuplicateError,
    ExternalServiceError,
    NotFoundError,
    ValidationError,
)


class TestErrorHierarchy:
    """All custom exceptions should work with AIResearchOSError catches."""

    def test_not_found(self):
        e = NotFoundError("Company", "abc-123")
        assert str(e) == "Company not found: abc-123"
        assert e.resource == "Company"
        assert e.id == "abc-123"
        assert isinstance(e, Exception)

    def test_validation_error(self):
        e = ValidationError("Invalid ticker symbol")
        assert str(e) == "Invalid ticker symbol"

    def test_duplicate_error(self):
        e = DuplicateError("Company", "AAPL")
        assert "already exists" in str(e)
        assert "Company" in str(e)

    def test_authentication_error(self):
        e = AuthenticationError()
        assert str(e) == "Not authenticated"

    def test_authorization_error(self):
        e = AuthorizationError()
        assert str(e) == "Insufficient permissions"

    def test_external_service_error(self):
        e = ExternalServiceError("yfinance", "Connection refused")
        assert "yfinance" in str(e)


class TestHealthEndpoint:
    """Quick smoke test — the /health endpoint."""

    def test_health_returns_ok(self, client: TestClient):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == settings.APP_NAME
        assert "version" in data

    def test_health_not_under_api_prefix(self, client: TestClient):
        """Health endpoint lives at root, not under /api/v1."""
        resp = client.get("/api/v1/health")
        assert resp.status_code == 404


class TestNotFoundHandler:
    """API should return structured 404s."""

    def test_unknown_route_returns_404(self, client: TestClient):
        resp = client.get("/api/v1/nonexistent")
        assert resp.status_code == 404

    def test_company_not_found_structured(self, client: TestClient):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = client.get(f"/api/v1/companies/{fake_id}")
        assert resp.status_code == 404
        data = resp.json()
        assert "detail" in data or "error" in data
