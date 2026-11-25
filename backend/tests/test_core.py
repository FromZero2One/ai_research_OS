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


class TestSchedulerJobs:
    """性能快照任务已随模块删除 — 调度器不应再注册它。"""

    def test_no_performance_snapshot_job(self):
        from pathlib import Path

        import core.scheduler

        source = Path(core.scheduler.__file__).read_text(encoding="utf-8")
        assert "performance_snapshot" not in source


class TestScreenerScheduleFailure:
    """定时选股失败路径：仅记日志，不抛异常，不做任何 Webhook 推送。"""

    async def test_failure_returns_failed_without_raising(self, monkeypatch):
        from sqlalchemy import delete

        from core.database import managed_session
        from core.screener_schedule import scheduled_screener_update
        from screener.models import ScreenerRun

        # 清掉测试库里残留的进行中 run，避免调度被跳过
        async with managed_session() as db:
            await db.execute(delete(ScreenerRun))
            await db.commit()

        monkeypatch.setattr(settings, "SCREENER_SCHEDULE_PRESETS", "core")

        async def boom(db, payload, enqueue=False):
            raise RuntimeError("模拟选股失败")

        monkeypatch.setattr("screener.service.trigger_run", boom)

        result = await scheduled_screener_update()
        entry = result["presets"]["core"]
        assert entry["status"] == "failed"
        assert "模拟选股失败" in entry["error"]
        assert "notification" not in entry and "webhook" not in entry

    def test_schedule_module_has_no_notify_dependency(self):
        from pathlib import Path

        import core.screener_schedule

        source = Path(core.screener_schedule.__file__).read_text(encoding="utf-8")
        assert "notify" not in source and "webhook" not in source.lower()
