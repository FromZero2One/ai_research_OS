# AI Research OS

> **Research First, not AI First** — AI is a capability in the research flow, not the center of the system.

A personal AI-powered investment research assistant. Company → Knowledge → AI → Research → Portfolio.

## 文档

- **[USAGE.md](USAGE.md)** — 全栈使用手册（启动、功能模块详解、投研流程、FAQ）
- **[backend/README.md](backend/README.md)** — 后端开发文档（数据库、API、配置、AI、测试）
- **[frontend/README.md](frontend/README.md)** — 前端开发文档（技术栈、目录、类型生成）

## Architecture

```text
                    User
                     │
              Research Workspace
              (Vue 3 Dashboard)
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

> **数据源架构**：A 股/港股统一走 akshare 子进程直连（Tencent/Sina/Eastmoney），数据落 PG（`market` schema）；美股走 yfinance（需代理）。无外部 MySQL 依赖。

## 7 Business Centers

| Center | Responsibility | Tech |
|--------|---------------|------|
| **Company Center** | Company profiles, industry, tags | PostgreSQL |
| **Market Center** | Stock prices, financials, macros (no analysis) | yfinance / AKShare |
| **Document Center** | Ingest → Parse → Chunk → Embed → Index（后台任务，PDF 表格结构化提取） | PyMuPDF + pdfplumber + BGE-M3 |
| **Knowledge Center** | Hybrid RAG: dense + sparse + rerank（中文停用词、查询扩展、命中高亮） | Qdrant + BM25 + RRF + BGE Reranker |
| **AI Center** | Prompt mgmt, LLM orchestration, summarization | DeepSeek V4 Flash (默认) / Ollama / OpenAI 兼容 |
| **Research Center** | Question → Evidence → Report → Decision → Thesis | LangGraph-ready |
| **Portfolio Center** | 关注公司（并入公司中心）、持仓、投资日志（后端） | PostgreSQL |

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

> 自选列表已并入 Company Center：`is_active` 即关注状态，`priority/target_price/reason` 挂在公司上。
> Portfolio Center 当前为持仓与投资日志（后端就绪，前端随 V2 P&L 一起提供）。

**Dependency rule**: Dependencies go UP only. Research can call Knowledge; Knowledge cannot call Research.

## Quick Start

**Windows 一键启动（推荐）**：双击项目根目录的 `start-dev.cmd` —— 自动起依赖栈（docker）+ 后端 :8000 + 前端 :5173，各在独立窗口运行。首次使用前需完成下方的依赖安装与 `alembic upgrade head`。

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
uv pip install --python .venv/bin/python jieba
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

## 当前进度

| 模块 | 完成度 | 备注 |
|------|:---:|------|
| 公司中心 | ~90% | CRUD/搜索/Thesis/自选（is_active）全可用 |
| 市场中心 | ~85% | A股行情/财务/估值 akshare 直连全链路 + 数据覆盖矩阵；美股 yfinance 备选 |
| 文档中心 | ~90% | 后台异步索引、PDF 表格结构化、切片内容类型打标、关联公司；OCR 待 V2 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 文档问答（模型切换）+ 检索评估集 + 内容类型过滤 |
| AI 中心 | ~75% | 模板/摘要/Token 用量全可用；AI 工作流已移除（单用户用不上） |
| 研究中心 | ~95% | 全链路 + LLM 证据分类（含定量/定性双轨）+ 多周期比对 + 报告可视化 + [ev:id] 引用回溯 + structured_facts 交叉验证 |
| 投资组合 | ~40% | 自选已并入公司；持仓/日志后端就绪，前端随 V2 |
| 系统/调度 | ~85% | 调度/观察/持久任务/事件/新鲜度可用 |

总体：V1.1 目标基本达成，后端 150 项测试通过（另有 4 项依赖 Ollama embeddings，无 Ollama 环境时不计）；ruff/vue-tsc/build 全绿。
已知缺口：美股真实行情、持仓/日志前端。下一步（比率层/覆盖矩阵定性维度/证据继承/差异日报）详见 [memory/ai-research-os-session.md](memory/ai-research-os-session.md)。

## API (when backend is running)

后端 API 前缀统一为 `/api/v1`，交互式文档见 http://localhost:8000/docs；接口速查见 [backend/README.md](backend/README.md)。

## Key Design Decisions

1. **No Knowledge Graph** — V2 upgrade path, not V1 complexity
2. **No LlamaIndex** — Hand-rolled SentenceTransformer + Qdrant for control
3. **No Trading Agents** — V2 feature, Research First
4. **Event Log** — Write-once audit trail for research process traceability
5. **Core Layer = Interfaces, not Implementations** — Protocols > concrete classes
6. **Workspace First, not Module First** — V1.1: Dashboard as default entry, not function list
7. **AI = Capability, not Center** — LLM provider swappable (DeepSeek/Ollama/OpenAI)
8. **自选列表并入公司中心** — watched == is_active，priority/target_price/reason 挂在公司上，消除两套列表重复
9. **文档表格结构化** — 财报类 PDF 表格按词坐标重建为 Markdown（保留集团/母公司列组），整块入库、问答不丢列含义

## Security Boundary

> **设计决策：本项目定位为单用户本地工具，API 默认不启用认证。** 请勿直接暴露到公网。

- 路由层未接入 JWT 认证（`core/security.py` 提供工具但未被使用）——这是有意的 V1 决策，不是疏漏
- `SECRET_KEY` 默认每次启动随机生成；若需跨重启保持 token 有效，请在 `backend/.env` 中显式设置
- CORS 默认仅允许 `http://localhost:5173`（开发前端），按需在 `.env` 中扩展
- 若未来需要部署到服务器/公网，第一优先级是接入认证（复用 `core/security.py`）并收紧基础设施访问

## Roadmap

已明确放弃：multi-agent、trading agents、LangGraph DAG 工作流（单用户工具过度设计，已于 2026-10 移除 AI 工作流）。

核心数据分工原则（2026-10-14）：**接口管"数"，PDF 管"事"** — Market 中心是数字唯一事实源；文档链路管定性正文（MD&A/风险/附注/公告）；structured_facts 仅作交叉验证质检器。

当前方向（分析师优先级排序）：

| 方向 | 状态 | 内容 |
|---|---|---|
| ~~数据质量看板~~ | ✅ | 覆盖矩阵 `GET /market/freshness/coverage` + Market 页卡片 |
| ~~报告引用回溯~~ | ✅ | 报告内联 `[ev:id]`，前端点击回跳证据卡（含定量/定性双轨打标） |
| ~~structured_facts 交叉验证~~ | ✅ | 财报抽取值 vs 接口值偏差≥10% → 观察事件（口径差异提示） |
| **比率层 + 历史分位** | 下一项 | 基于标准枚举指标计算毛利率/ROE/负债率等派生比率；PE/PB 历史分位（akshare 历史估值序列） |
| **覆盖矩阵定性维度** | 未开始 | 覆盖矩阵扩展"定性覆盖"：是否有已索引年报正文（mda/risk 章节） |
| **证据继承** | 未开始 | 同一公司跨研究 session 复用历史证据并标注"历史已核实" |
| **差异日报** | 未开始 | 晨报改为只报变化：新公告、财报日历临近、价格异动、证据与旧结论冲突 |
