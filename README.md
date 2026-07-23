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

# 2. Create tables and seed data
cd backend
pip install -e ".[dev]"
python scripts/seed_data.py

# 3. Start backend
ALL_PROXY= all_proxy= PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

# 4. Start frontend (separate terminal)
cd frontend
npm install
npm run dev
```

> **LLM config**: By default the system uses **DeepSeek V4 Flash** (cloud API).
> Set `OPENAI_API_KEY` in `backend/.env` before using AI features.
> See [USAGE.md](USAGE.md) for alternative providers (Ollama, other OpenAI-compatible APIs).

Visit **http://localhost:3000** — the Research Workspace dashboard.

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

## V1 → V1.1 → V2 → V3

| | V1 | V1.1 ✅ | V2 | V3 |
|---|---|---|---|---|
| Knowledge | Hybrid RAG | + RRF Fusion | + Knowledge Graph | + Causal Reasoning |
| AI | Single LLM (Ollama) | + DeepSeek V4 Flash | + LangGraph DAGs | + Multi-agent |
| Portfolio | Watchlist + Journal | + Thesis Panel | + P&L Tracking | + Execution |
| Research | Manual + Assist | + One Click + Timeline | + Auto Research | + Trading Agents |
| Workspace | Module pages | Dashboard + Observations | — | — |
