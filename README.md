# AI Research OS

> **Research First, not AI First** — AI is a capability in the research flow, not the center of the system.

A personal AI-powered investment research assistant. Company → Knowledge → AI → Research → Portfolio.

## Architecture

```text
                    User
                     │
              Research Workspace
              (Next.js Dashboard)
                     │
                     ▼
              API Gateway (FastAPI)
                     │
   ┌────────────────────────────────┐
   │       Application Layer        │
   ├────────────────────────────────┤
   │  Company     │   Research      │
   │  Center      │   Center        │
   │              │                 │
   │  Market      │   AI            │
   │  Center      │   Center        │
   │              │                 │
   │  Document    │   Portfolio     │
   │  Center      │   Center        │
   │              │                 │
   │  Knowledge   │                 │
   │  Center      │                 │
   └────────────────────────────────┘
                     │
   ┌────────────────────────────────┐
   │          Core Layer            │
   ├────────────────────────────────┤
   │  DB  │  Vector  │  LLM  │  Cache│
   └────────────────────────────────┘
```

> **关于 MySQL**: 本项目数据库为 PostgreSQL（docker-compose 内）。代码中引用的 MySQL 属于外部 akshare 数据源自管的数据库，非本项目 docker-compose 的一部分。A 股行情需要额外配置该外部 MySQL 连接。

## 7 Business Centers

| Center | Responsibility | Tech |
|--------|---------------|------|
| **Company Center** | Company profiles, industry, tags | PostgreSQL |
| **Market Center** | Stock prices, financials, macros (no analysis) | yfinance / AKShare |
| **Document Center** | Ingest → Parse → Chunk → Embed → Index | PyMuPDF + BGE-M3 |
| **Knowledge Center** | Hybrid RAG: dense + sparse retrieval | Qdrant + BM25 + RRF |
| **AI Center** | Prompt mgmt, LLM orchestration, summarization | DeepSeek V4 Flash (默认) / Ollama / OpenAI 兼容 |
| **Research Center** | Question → Evidence → Report → Decision → Thesis | LangGraph-ready |
| **Portfolio Center** | Watchlists, holdings, investment journal | PostgreSQL |

## Data Flow

```text
Company
  ↓
Market + Document
  ↓
Knowledge (Hybrid RAG)
  ↓
AI (LLM)
  ↓
Research (Thesis → Decision)
  ↓
Portfolio
```

**Dependency rule**: Dependencies go UP only. Research can call Knowledge; Knowledge cannot call Research.

## Quick Start

```bash
# 1. Start infrastructure
make dev-db

# 2. Install backend dependencies (install uv first if not present: curl -LsSf https://astral.sh/uv/install.sh | sh)
cd backend
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python \
  "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.0" "pydantic-settings>=2.0" \
  "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.29" "alembic>=1.13" "pgvector>=0.3" \
  "ollama>=0.4" "openai>=1.0" "langgraph>=0.2" \
  "qdrant-client>=1.11" "rank-bm25>=0.2" \
  "pymupdf>=1.24" "markdown>=3.0" "apscheduler>=3.10" \
  "redis[hiredis]>=5.0" "httpx>=0.27" "python-multipart>=0.0.12" \
  "python-jose[cryptography]>=3.3" "passlib[bcrypt]>=1.7" \
  "structlog>=24.0" "opentelemetry-api>=1.25" "opentelemetry-sdk>=1.25" \
  "pytest>=8.0" "pytest-asyncio>=0.24" "pytest-cov>=5.0" "ruff>=0.6" "mypy>=1.11"
uv pip install --python .venv/bin/python jieba pymysql
# Optional: sentence-transformers (CUDA ~3GB, fallback when Ollama unavailable)
# uv pip install --python .venv/bin/python "sentence-transformers>=3.0"

# 3. Create tables and seed data
source .venv/bin/activate
PYTHONPATH=. alembic upgrade head
PYTHONPATH=. python scripts/seed_data.py

# 4. Start backend
ALL_PROXY= all_proxy= PYTHONPATH=. .venv/bin/python -m uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

# 5. Start frontend (separate terminal)
cd frontend
npm install   # first time only
npm run dev   # starts on http://localhost:5173
```

> **LLM config**: By default the system uses **DeepSeek V4 Flash** (cloud API).
> Set `OPENAI_API_KEY` in `backend/.env` before using AI features.
> See [USAGE.md](USAGE.md) for alternative providers (Ollama, other OpenAI-compatible APIs).

Visit **http://localhost:5173** — the Research Workspace dashboard.

## API (when backend is running)

| Module | API Prefix | Docs |
|--------|-----------|------|
| All | `/api/v1/...` | http://localhost:8000/docs |
| Health | `/health` | — |

## Key Design Decisions

1. **No Knowledge Graph** — V2 upgrade path, not V1 complexity
2. **No LlamaIndex** — Hand-rolled SentenceTransformer + Qdrant for control
3. **No Trading Agents** — V2 feature, Research First
4. **Event Log** — Write-once audit trail for research process traceability
5. **Core Layer = Interfaces, not Implementations** — Protocols > concrete classes
6. **Workspace First, not Module First** — V1.1: Dashboard as default entry, not function list
7. **AI = Capability, not Center** — LLM provider swappable (DeepSeek/Ollama/OpenAI)

## Security Boundary

> **设计决策：本项目定位为单用户本地工具，API 默认不启用认证。** 请勿直接暴露到公网。

- 路由层未接入 JWT 认证（`core/security.py` 提供工具但未被使用）——这是有意的 V1 决策，不是疏漏
- `SECRET_KEY` 默认每次启动随机生成；若需跨重启保持 token 有效，请在 `backend/.env` 中显式设置
- CORS 默认仅允许 `http://localhost:5173`（开发前端），按需在 `.env` 中扩展
- 若未来需要部署到服务器/公网，第一优先级是接入认证（复用 `core/security.py`）并收紧基础设施访问

## V1 → V1.1 → V2 → V3

| | V1 | V1.1 ✅ | V2 | V3 |
|---|---|---|---|---|
| Knowledge | Hybrid RAG | + RRF Fusion | + Knowledge Graph | + Causal Reasoning |
| AI | Single LLM (Ollama) | + DeepSeek V4 Flash | + LangGraph DAGs | + Multi-agent |
| Portfolio | Watchlist + Journal | + Thesis Panel | + P&L Tracking | + Execution |
| Research | Manual + Assist | + One Click + Timeline | + Auto Research | + Trading Agents |
| Workspace | Module pages | Dashboard + Observations | — | — |
| **Infra** | asyncio.create_task | **Persistent Tasks** + Worker | — | — |
| **Infra** | Raw SQL in routes | **Service Layer** + Unified Routers | — | — |
| **Infra** | EventLog write-only | **Read API** + Frontend Type Gen | — | — |
| **Infra** | — | **Data Freshness** Tracking | — | — |
