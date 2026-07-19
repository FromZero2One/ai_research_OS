#!/bin/bash
set -e
cd "$(dirname "$0")/../backend"

echo "=== Installing Python dependencies ==="

# Core web framework
pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.0" "pydantic-settings>=2.0"

# Database
pip install "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.29" "alembic>=1.13" "pgvector>=0.3"

# AI / LLM
pip install "openai>=1.0" "langgraph>=0.2"

# Search / Vector
pip install "qdrant-client>=1.11" "rank-bm25>=0.2"

# Document processing
pip install "pymupdf>=1.24"

# Scheduling
pip install "apscheduler>=3.10"

# Utilities
pip install "redis[hiredis]>=5.0" "httpx>=0.27" "python-multipart>=0.0.12" "python-jose[cryptography]>=3.3" "passlib[bcrypt]>=1.7"

# Observability
pip install "structlog>=24.0"

# Embeddings (large download - separate)
pip install "sentence-transformers>=3.0"

# Dev
pip install "pytest>=8.0" "pytest-asyncio>=0.24" "httpx>=0.27"

echo "=== All dependencies installed ==="
