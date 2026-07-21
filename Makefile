.PHONY: dev dev-db dev-backend dev-frontend migrate lint clean

# ── Development ──────────────────────────────────────────────────────

dev: dev-db migrate dev-backend
	@echo "AI Research OS running on http://localhost:3000"

dev-db:
	docker compose -f docker/docker-compose.yml up -d
	@echo "Waiting for PostgreSQL..."
	@sleep 3

dev-backend:
	cd backend && ALL_PROXY= all_proxy= no_proxy="localhost,127.0.0.0/8,::1" uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

dev-frontend:
	cd frontend && npm run dev

# ── Database ─────────────────────────────────────────────────────────

migrate:
	cd backend && alembic upgrade head

migration:
	cd backend && alembic revision --autogenerate -m "$(message)"

reset-db:
	docker compose -f docker/docker-compose.yml down -v
	docker compose -f docker/docker-compose.yml up -d
	@sleep 3
	cd backend && alembic upgrade head

# ── Quality ──────────────────────────────────────────────────────────

lint:
	cd backend && ruff check . && ruff format --check .

format:
	cd backend && ruff format . && ruff check --fix .

typecheck:
	cd backend && mypy .

test:
	cd backend && pytest -v

test-cov:
	cd backend && pytest --cov=. --cov-report=term-missing

# ── Data ─────────────────────────────────────────────────────────────

ingest-sample:
	cd backend && python scripts/seed_data.py

# ── Docker ───────────────────────────────────────────────────────────

docker-up:
	docker compose -f docker/docker-compose.yml up -d

docker-down:
	docker compose -f docker/docker-compose.yml down

docker-logs:
	docker compose -f docker/docker-compose.yml logs -f

# ── Cleanup ─────────────────────────────────────────────────────────

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete
	rm -rf backend/data/uploads/*
