@echo off
REM AI Research OS one-click start: deps + backend + frontend
set ROOT=%~dp0

echo [1/3] Starting docker deps (Postgres/Qdrant/Redis)...
docker compose -f "%ROOT%docker\docker-compose.yml" up -d

echo [2/3] Starting backend uvicorn :8000 (new window)...
start "AI-OS-Backend-8000" cmd /k "cd /d %ROOT%backend && set PYTHONPATH=. && python -X utf8 -m uvicorn api.app:app --host 127.0.0.1 --port 8000"

echo [3/3] Starting frontend vite :5173 (new window)...
start "AI-OS-Frontend-5173" cmd /k "cd /d %ROOT%frontend && npm run dev"

echo.
echo ================================================
echo   Frontend : http://localhost:5173
echo   Backend  : http://127.0.0.1:8000  (docs at /docs)
echo ================================================
echo Services run in separate windows; close a window to stop it.
echo Deps stay running (stop: docker compose -f docker\docker-compose.yml down)
echo If browser shows nothing yet, wait a few seconds (vite cold start ~5-10s).
pause
