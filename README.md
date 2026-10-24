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
| **Market Center** | Stock prices, financials, valuation history percentiles, ratio layer (no analysis) | yfinance / AKShare |
| **Document Center** | Ingest → Parse → Chunk → Embed → Index（后台任务，PDF 表格结构化提取） | PyMuPDF + pdfplumber + BGE-M3 |
| **Knowledge Center** | Hybrid RAG: dense + sparse + rerank（中文停用词、查询扩展、命中高亮） | Qdrant + BM25 + RRF + BGE Reranker |
| **AI Center** | Prompt mgmt, LLM orchestration, summarization | DeepSeek V4 Flash (默认) / Ollama / OpenAI 兼容 |
| **Research Center** | Question → Evidence → Report → Decision → Thesis | LangGraph-ready |
| **Portfolio Center** | 关注公司（并入公司中心）、持仓、投资日志（后端） | PostgreSQL |
| **Screener** | 预设标准库选股：42 指标（TTM 估值 + 现金流质量 + 因子深度 + 银行/保险专属）+ 8 内置预设 + 股票池卫生 + 行业隔离/相对排名 + 三态结论 + 定时筛选/变化日报 + 推荐后表现跟踪 + 组合构建 + LLM 深判评测 + 推荐股送入研究中心 + 变化日报 Webhook + 失败告警 + 调度状态/立即运行 + CSV 导出 + 组合保存 + 回测面板/分段稳健性 + 运行明细/逐只送入研究与自选 + 数据质量面板/运行筛选 + 表现快照定时记录 + 组合再平衡 + 运行取消 + 近似命中报告（2026-10-24） | AKShare + LLM 深判 |

> **Screener 数据管道（2026-10-22）**：全市场快照走新浪源（东财风控应对）；财务三表（业绩/资产负债/现金流）均为市场级一次调用（~5000 只/期），不再逐只拉取；流动/速动/周转/成长率走东财 F10 主要指标（`RPT_F10_FINANCE_MAINFINADATA`）分页补采。已知缺口见 Roadmap。

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
>
> **比率层数据流（2026-10-15）**：`financial_metrics` → `compute_ratios` 纯函数 → `/market/ratios/{ticker}`；
> `valuation_history`（PG，首次经 akshare `stock_a_indicator_lg` 拉全量）→ `percentile_rank` → `/market/ratios/{ticker}/valuation-percentile`；
> 两者经 `build_ratio_block` 进报告上下文（标注"禁止改写"，与 period/peer 区块并列）。

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
| 市场中心 | ~90% | A股行情/财务/估值 akshare 直连全链路 + 数据覆盖矩阵（含量性维度）+ 比率层 + PE/PB 历史分位；美股 yfinance 备选 |
| 文档中心 | ~90% | 后台异步索引、PDF 表格结构化、切片内容类型打标、关联公司；OCR 待 V2 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 文档问答（模型切换）+ 内容类型过滤 |
| AI 中心 | ~60% | Prompt 模板管理/执行 + Token 用量；摘要/提取已砍（与 RAG 问答重叠，AI 能力内嵌研究流程） |
| 研究中心 | ~95% | 全链路 + LLM 证据分类（含定量/定性双轨）+ 多周期比对 + 报告可视化 + [ev:id] 引用回溯 + structured_facts 交叉验证 |
| 投资组合 | ~40% | 自选已并入公司；持仓/日志后端就绪，前端随 V2 |
| 系统/调度 | ~85% | 调度/观察/持久任务/事件/新鲜度可用 |
| 智能选股 | ~95% | 42 指标（TTM 估值 + 现金流质量 + 因子深度 + 银行/保险专属）+ 8 内置预设；股票池卫生 + 行业隔离/相对排名；深判知识库/证据守卫 + 三态结论 + 评测器；预设回测（Sharpe/Sortino/Calmar）；定时筛选 + 变化日报 + 推荐后表现（含沪深300超额）+ 组合构建 + 推荐股送入研究中心 + 变化日报/失败告警 Webhook（企微/飞书/钉钉）+ 调度状态/立即运行 + CSV 导出 + 组合保存/再平衡 + 回测面板/分段稳健性 + 表现快照 + 运行取消 + 近似命中；财务数据工作日定时更新 |

总体：V1.1 目标基本达成，后端 **391 passed / 2 failed / 2 skipped**（2 项失败为既有 research 证据继承依赖本地 LLM 结构化输出，与选股改动无关）；screener + financial_sync 专项 **324 passed**；前端 vue-tsc/build 通过。改动文件 ruff 通过（仓库仍保留历史 E501 债务）。
已知缺口：美股真实行情、持仓/日志前端、Market.vue 覆盖网格列数动态化（当前硬编码 5 列）。下一步（证据继承/差异日报）详见 [memory/ai-research-os-session.md](memory/ai-research-os-session.md)。

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
| ~~比率层 + 历史分位~~ | ✅ 2026-10-15 | `market/ratio_service.py` 派生毛利率/净利率+透出 ROE/负债率/周转率等；`market.valuation_history` 表（akshare `stock_a_indicator_lg` 全序列入 PG）算 PE/PB 历史分位；API `/market/ratios/{ticker}[/valuation-percentile]`；报告区块 + CompanyDetail 卡片 |
| ~~覆盖矩阵定性维度~~ | ✅ 2026-10-15 | 矩阵新增定性列：已索引文档含 mda/risk 切片 → ok；仅已索引 → partial；无 → missing；纳入 worst_health |
| ~~证据继承~~ | ✅ 2026-10-16 | auto-gather 自动带入同公司已完成会话证据（上限 10 条/去重/幂等），标 inherited_from_session_id，前端「📥 历史已核实」徽标可跳原会话 |
| **差异日报** | 未开始 | 旧晨报已删（2026-10-14），从零构建"只报变化"日报：新公告、财报日历临近、价格异动、证据与旧结论冲突 |
| ~~预设标准库（Screener v1.5）~~ | ✅ 2026-10-24 | 42 指标（TTM 估值 + 现金流质量 + 因子深度 + 银行/保险专属）+ 8 内置预设（含银行/保险价值）+ 组合模式；股票池卫生；申万行业分类与金融行业隔离；回测风险指标（Sharpe/Sortino/Calmar/年化超额） |

收尾待办（小项）：Market.vue 覆盖网格列数动态化（当前硬编码 `repeat(5, 90px)`）；test_finalize_session 补 LLM mock（真实 LLM 调用挂起）；qualColor 硬编码色值统一 CSS 变量。

Screener 后续（2026-10-22 排序）：

1. ~~财务数据更新调度~~ ✅ 2026-10-24 — `core/financial_sync.py` 挂 APScheduler（`FINANCIAL_DATA_SCHEDULE`，工作日 3:15），三类数据源 SAVEPOINT 隔离，`/scheduler/status` 可见
2. ~~全链路真实端到端验证~~ ✅ 2026-10-22 — 深度价值 50 候选/21 推荐；高成长 106 候选（营收/净利同比规则生效）；F10 指标覆盖 98%+
3. ~~预设回测~~ ✅ 2026-10-23 — MVP 已交付：`POST /screener/backtests`（5 年季度调仓、外部 MySQL 前复权日线、akshare 历史财务按需补拉、年报口径无未来函数、近似市值声明）；结果 {summary, yearly} + Markdown 报告落盘；见 `backend/screener/backtest*.py`
4. ~~报告数据时效标注~~ ✅ 2026-10-22 — 报告概览标注「财务数据截至 2026Q2（2026-06-30）」
5. **数据源去单点** — 财务/新闻仍依赖东财；外部 MySQL（8.137.104.120，缺财务三表）可升级为首选源，akshare 降为兜底
