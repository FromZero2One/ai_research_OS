# AGENTS.md

Personal AI investment-research assistant. FastAPI backend in `backend/` (Python, uv venv at `backend/.venv`) + Vue 3/Vite frontend in `frontend/`. Full docs: `README.md`, `USAGE.md`, `backend/README.md`, `frontend/README.md` — written in Chinese; keep that when editing them. Progress/known-gaps snapshot: `memory/ai-research-os-session.md`.

## Commands

- **Start (Windows)**: `start-dev.cmd` — docker deps + backend :8000 + frontend :5173 in separate windows. Manual equivalent: `docker compose -f docker/docker-compose.yml up -d` (Postgres :5432, Qdrant :6333, **Redis :6380**, not 6379), then backend, then `cd frontend && npm run dev`.
- **Backend must start from `backend/`** — `UPLOAD_DIR=data/uploads` is a relative path. Use `start-backend.ps1` / `start-dev.cmd`, or `cd backend` then `PYTHONPATH=. uvicorn api.app:app --reload --port 8000`.
- **First run**: deps stack up → `cd backend && PYTHONPATH=. alembic upgrade head` → `PYTHONPATH=. python scripts/seed_data.py` → needs `OPENAI_API_KEY` in `backend/.env` for AI features.
- **Tests** (from `backend/`, docker Postgres + Qdrant must be up): `.venv\Scripts\python -m pytest -v`; single file/test: `... pytest tests/test_market.py -k name` (pytest-asyncio `auto` mode — no markers needed). conftest auto-creates the dedicated `airesearch_test` DB (override via `TEST_DATABASE_URL`) and **refuses to run against the dev DB**; vectors go to a separate `documents_test` Qdrant collection.
- **Known-failing tests**: 2 research evidence-inheritance tests fail because the local LLM returns truncated JSON (per README). Pre-existing — don't chase them in unrelated changes.
- **Migrations**: from `backend/`, `PYTHONPATH=. alembic upgrade head` / `alembic revision --autogenerate -m "..."`. Linear chain (~30 versions).

## Lint / typecheck debt — important

- **Full `ruff check` and `ruff format --check` fail repo-wide** (~200 errors, ~100 unformatted files — historical debt). Only run ruff on files you touched; never run repo-wide `ruff format` (would create a massive diff).
- mypy scope is deliberately narrow (`core`, `market/domain.py`, `market/repositories.py`, `research/schemas.py`) — see `[tool.mypy]` in `backend/pyproject.toml`.
- pre-commit enforces ruff --fix + format on changed files and the scoped mypy: `pre-commit run --files <changed files>`.

## Environment quirks

- Proxy env vars (`ALL_PROXY`, `HTTP(S)_PROXY`) break httpx calls to localhost. `api/app.py` calls `core/proxy_cleanup.clean_proxy_env()` before importing routers; standalone scripts using adapters directly must call it too (or clear the vars — the `ALL_PROXY= all_proxy=` prefix in docs/scripts).
- Config: `core/config.py` (pydantic-settings, reads `backend/.env`). Code defaults differ from this machine's `.env` (LLM: DeepSeek via OpenAI-compatible endpoint, not the Ollama default). Full variable table in `backend/README.md`.
- Hardcoded `/home/wsm/...` paths (`.env.example`, `backend/run_dev.sh`, Makefile `refresh-market` target) come from the original Linux dev box — machine-specific. On Windows use `start-dev.cmd` and set real paths in `backend/.env`.

## Architecture rules

- Modules under `backend/`: company, market, document, knowledge, research, portfolio, screener (+ core, api, ai, dashboard). **Dependencies go up only**: company → market/document → knowledge → research → portfolio. Knowledge/dashboard have no own DB schema (reuse `document` tables / cross-schema aggregation).
- **Data division**: Market center is the ONLY source of numbers (akshare → PG `market` schema); Document/Knowledge handle qualitative text; `structured_facts` is cross-validation only. Don't source numbers from PDFs.
- DI via `core/container.py`; routes get services through `Depends(get_container)`. Errors flow through `core/exceptions.py` handlers (structured JSON: 404/422/409/502/...). Timestamps are UTC ISO-8601 everywhere.
- PostgreSQL: one schema per module (company/market/document/research/portfolio/ai/core/screener). `core.event_log` is a write-once audit trail — never update/delete.
- Screener: deterministic screening; LLM only for per-stock deep judgement. Metric/preset definitions in `screener/seeds.py`; Markdown reports land in `screener/reports/`.
- Backend tasks: persistent PG-backed queue (`core/task_manager.py`) + APScheduler jobs in `core/scheduler.py` (see `GET /api/v1/scheduler/status`).

## Conventions

- **No auth by design** — single-user local tool; `core/security.py` exists but is intentionally unused. Don't add JWT or expose the API publicly. CORS allows `http://localhost:5173` only.
- API prefix is always `/api/v1`; FastAPI docs at http://localhost:8000/docs.
- Frontend data access goes through `src/stores/api.ts` (TanStack Query hooks) — views don't call `fetch` directly. `npm install` depends on `legacy-peer-deps=true` in `frontend/.npmrc` — don't delete it. Typecheck via `npm run build` (`vue-tsc -b` runs first). OpenAPI type gen (`npm run gen`) is optional; the app uses hand-written calls.
- Commits: conventional commits (`feat:`, `docs:`, `fix:`, `chore:`), straight to `main`. **No CI** — local ruff/mypy/pytest is the only verification gate.
- Root-level scripts (`check_pg*.py`, `ingest_*.py`, `get_main_board.py`, ...) are one-off data-ingestion/DB-inspection scratch files, not part of the app.
