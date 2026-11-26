# AI Research OS 使用手册

> **Screener First, not AI First** — 数据与规则管筛选，运行链路全系统零 LLM（仅 Ollama embedding 保留）。

> **2026-11-24 项目瘦身**：研究中心、投资组合、AI 中心（Prompt 模板）、仪表盘四个模块的代码已删除，系统聚焦价值筛选核心链路。数据库表保留。
>
> **2026-11-25 二次瘦身（价值推荐聚焦）**：组合构建/再平衡、表现跟踪与快照、回测交互路由（引擎保留为脚本）、freeform 自由文本模式、运行取消、近似命中、前端 Knowledge 页/PresetManager/ReportCharts 均已删除；预设只读化；新增事实检查确定性化（`fact_checks.py`）与 `GET /api/v1/screener/latest-report`；报告改为四段投资理由结构。本手册已按裁剪后架构更新。
>
> **2026-11-25 三次简化（深判退役）**：LLM 深判整体退役、变化日报/失败告警 Webhook 全删、回测去框架化（脚本直调纯函数落 JSON）、CSV 导出与自选推送端点删除、历史排查脚本归档 `backend/tools/archive/`。运行链路 = 预设量化初筛 → 事实检查确定性判定 → 三段报告 → `latest-report`，零 LLM、单轮 ≤2 分钟（知识库问答仍用 LLM）。本手册已按三次简化口径更新。
>
> **2026-11-26 六次简化**：知识库问答退役（删 `/knowledge/ask`、`/knowledge/llm/models` 及 LLM 适配器与相关配置，全系统零 LLM，仅 Ollama embedding 保留）；公司中心退役（删 CRUD/thesis/watch API 与前端公司页，仅保留 `GET /companies` 供文档「关联公司」下拉）；删 `news_service.py` 与 `ScreenerBacktestRun` ORM 类（表保留）；cash_coverage 券商口径豁免（exempt 视同通过）；报告新增「较上一轮」轮次对比；confidence 字段退役（报告与前端删「置信度」列，ORM 列保留恒空）；预设证据分层（`PRESET_EVIDENCE` grade 徽标），`SCREENER_SCHEDULE_PRESETS` 默认改 `financial,value`。本手册已按六次简化口径更新。

---

## 一、项目架构

```
┌──────────────────────────────────────────────┐
│  前端: Vue 3 + Vite (localhost:5173)         │
│  后端: FastAPI (localhost:8000)              │
│  API文档: localhost:8000/docs (Swagger UI)   │
└──────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────┐
│  PostgreSQL (pgvector)  ← 公司/行情/财务/选股│
│  Qdrant (向量数据库)    ← 知识库索引         │
│  Redis                  ← 缓存               │
└──────────────────────────────────────────────┘
              ↓ 数据采集（子进程直连）
┌──────────────────────────────────────────────┐
│  akshare (A股/港股: Tencent/Sina/Eastmoney)  │
│  yfinance (美股，需代理)                     │
└──────────────────────────────────────────────┘
              ↓ AI能力
┌──────────────────────────────────────────────┐
│  Ollama (本地 Embedding，仅文档索引用)        │
└──────────────────────────────────────────────┘
```

> **数据源说明**: A 股/港股数据经 akshare 子进程直连采集（无外部数据库依赖），统一落 PostgreSQL（`market` schema）；docker-compose 仅包含 PostgreSQL、Qdrant、Redis。

### 核心技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3, Vite, TypeScript, Element Plus, TanStack Vue Query, ECharts |
| 后端 | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic |
| 数据库 | PostgreSQL 16 (pgvector), Qdrant, Redis |
| AI | 无 LLM（全系统零 LLM）；仅 Ollama 本地 Embedding（BGE-M3） |
| 文档处理 | PyMuPDF + pdfplumber（财报表格结构化）, BGE-M3 向量化, 后台异步索引 |
| 知识检索 | Qdrant 稠密 + BM25 稀疏 + RRF 融合 + BGE Reranker（知识库问答已退役） |
| 基础设施 | Docker Compose |

---

## 二、服务启动与停止

### Windows 一键启动（推荐）

双击项目根目录的 **`start-dev.cmd`**：自动启动依赖栈（docker compose）、后端 uvicorn（:8000）和前端 vite（:5173），各在独立命令行窗口运行（关窗口即停该服务，依赖栈保持后台）。

> 首次使用前仍需完成下方 Step 2（安装依赖）、Step 4（迁移）一次性初始化。

### 启动顺序

#### Step 1 — 启动数据库基础设施

```bash
cd /home/wsm/codes/ai_research_OS
docker compose -f docker/docker-compose.yml up -d
```

验证启动成功:
```bash
docker compose -f docker/docker-compose.yml ps
```

应有3个容器: `airesearch-postgres` (healthy), `airesearch-qdrant` (healthy), `airesearch-redis` (healthy)

---

#### Step 2 — 安装后端依赖

> 推荐使用 `uv`（已安装），速度远快于 pip。首次使用需创建虚拟环境。

**方式 A — uv（推荐）：**

```bash
cd /home/wsm/codes/ai_research_OS/backend
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python \
  "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.0" "pydantic-settings>=2.0" \
  "sqlalchemy[asyncio]>=2.0" "asyncpg>=0.29" "alembic>=1.13" "pgvector>=0.3" \
  "ollama>=0.4" "openai>=1.0" "langgraph>=0.2" \
  "qdrant-client>=1.11" "rank-bm25>=0.2" \
  "pymupdf>=1.24" "markdown>=3.0" \
  "apscheduler>=3.10" \
  "redis[hiredis]>=5.0" "httpx>=0.27" "python-multipart>=0.0.12" \
  "python-jose[cryptography]>=3.3" "passlib[bcrypt]>=1.7" \
  "structlog>=24.0" "opentelemetry-api>=1.25" "opentelemetry-sdk>=1.25" \
  "pytest>=8.0" "pytest-asyncio>=0.24" "pytest-cov>=5.0" "ruff>=0.6" "mypy>=1.11"
```

**方式 B — pip：**

```bash
cd /home/wsm/codes/ai_research_OS/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

> **注意**: `pip install -e` 方式需要 `pyproject.toml` 包含 `[tool.setuptools.packages.find]` 配置，否则会因 flat-layout 多包结构报错。请确保该配置存在后再执行。

**安装额外依赖：**

```bash
source .venv/bin/activate
uv pip install --python .venv/bin/python jieba  # BM25 中文分词（必须）
# 可选：sentence-transformers 作为嵌入备用（需下载 CUDA 包 ~3GB）
# uv pip install --python .venv/bin/python "sentence-transformers>=3.0"
```

> **关于 sentence-transformers**（可选依赖）: 项目主要嵌入走 Ollama API（BGE-M3），`sentence-transformers` 仅作备用。安装它会拉取 torch + CUDA（约 3GB）。需要时通过 `uv pip install --python .venv/bin/python "sentence-transformers>=3.0"` 或 `pip install "ai-research-os[embedding]"` 安装。详情见 [Ollama 安装指南](https://ollama.ai)。

---

#### Step 3 — 启动后端

> **注意**: 必须从 `backend/` 目录启动 uvicorn，否则 `.env` 文件不会被加载。

```bash
cd /home/wsm/codes/ai_research_OS/backend
ALL_PROXY= all_proxy= PYTHONPATH=. .venv/bin/python -m uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

> **SOCKS 代理注意事项**: 如果你本地启用了 SOCKS 代理（如 Clash），需要 `ALL_PROXY= all_proxy=` 前缀来绕过代理连接本地 PostgreSQL/Qdrant/Redis。

**启动时行为**: 后端启动会依次执行:
1. 连接 PostgreSQL 验证
2. 预热 Embedding 模型（Ollama BGE-M3，后台加载，不阻塞启动）
3. 启动 Scheduler（如已启用）

---

#### Step 4 — 启动前端

> 前端是基于 Vue 3 + Vite 的 SPA，需要在 `frontend/` 目录下操作。

```bash
cd /home/wsm/codes/ai_research_OS/frontend

# 首次使用需安装依赖
npm install

# 启动开发服务器（默认端口 5173）
npm run dev
```

> **前端端口**: Vite 开发服务器默认运行在 **5173 端口**（不是 3000）。vite.config.ts 已配置 `/api` 代理到 `localhost:8000`（自动加 `/v1` 前缀），无需额外配置。
>
> 如需修改端口，在 `package.json` 的 `dev` 脚本中加 `--port` 参数:
> ```bash
> npm run dev -- --port 3000
> ```

---

#### Step 5 — (可选) 配置 Embedding 服务

> **LLM 配置已退役**（2026-11-26）：`LLM_PROVIDER`、`OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`、`OLLAMA_MODEL`、`OLLAMA_NUM_CTX`、`EVIDENCE_CLASSIFIER` 等变量已不再使用，无需配置。

系统全链路零 LLM，唯一 AI 依赖是文档索引的 Embedding（默认走 Ollama 本地 BGE-M3）：

```bash
# 启动 Ollama 服务（若未运行）
ollama serve

# 下载 embedding 模型
ollama pull bge-m3
```

对应 `.env` 配置（可选，默认即是）：

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=bge-m3
```

---

### 停止服务

```bash
# 停止后端 (Ctrl+C 或 kill)
kill $(lsof -ti:8000) 2>/dev/null

# 停止前端 (Ctrl+C 或 kill)
kill $(lsof -ti:5173) 2>/dev/null

# 停止所有数据库容器
docker compose -f docker/docker-compose.yml down

# 停止并清除数据卷 (完全重置)
docker compose -f docker/docker-compose.yml down -v
```

---

### 快速启动脚本 (Makefile)

项目根目录提供了 Makefile 快捷命令:

```bash
make dev         # 启动DB + 迁移 + 后端 (前端需单独启动)
make dev-db      # 仅启动数据库
make dev-backend # 仅启动后端
make dev-frontend # 仅启动前端
make migrate     # 运行数据库迁移
make reset-db    # 删除并重建数据库
make test        # 运行测试
make ingest-sample # 加载示例数据
```

---

## 三、访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端首页 | http://localhost:5173 | Vue 3 + Vite SPA (默认端口) |
| 后端API | http://localhost:8000 | — |
| API文档 | http://localhost:8000/docs | Swagger UI (交互式) |
| ReDoc | http://localhost:8000/redoc | 替代文档 |
| Qdrant控制台 | http://localhost:6333 | 向量数据库管理 |
| PostgreSQL | localhost:5432 | 用户:airesearch, 密码:airesearch_dev |
| Redis | localhost:6380 | (端口6380映射到容器6379) |

---

## 四、功能模块详解

### 4.1 智能选股首页 `/screener`

**访问地址**: http://localhost:5173 （首页即智能选股，2026-11-24 瘦身后）

全市场价值股筛选是系统的核心出口，详见下方「4.6 智能选股」。

---

### 4.2 公司中心（已退役，2026-11-26）

公司中心 API 与前端页面已删除：CRUD、标签、Thesis、自选（watch/`is_active`）均不再可用，前端 Companies/CompanyDetail 页面与 Sidebar/路由/命令面板入口已移除。

**保留**：`GET /api/v1/companies` 仅供文档中心「关联公司」下拉使用。Company 表与 ORM 模型保留（screener 数据质量统计、market search/profile/freshness、document.company_id 外键仍读）。

---

### 4.3 市场中心 `/market`

功能:查询股票行情和财务数据。

**美股数据** (字母代码, 如 `AAPL`):

需要先采集数据到本地数据库:
```
POST /api/v1/market/prices/AAPL/ingest?provider=yfinance  # 采集1年数据到PG
GET  /api/v1/market/prices/AAPL                            # 查询采集的数据
```

**A股数据** (6位数字代码, 如 `600519` 茅台):

无需任何外部数据库——akshare 子进程直连采集，首次查询自动拉取并落 PG 缓存:
```
GET /api/v1/market/prices/600519       # 日K线数据（PG 缓存 → akshare 直连）
GET /api/v1/market/search?query=茅台    # 搜索公司（PG Companies 表）
GET /api/v1/market/financials/600519   # 财务指标(EPS/营收/ROE等, 财务摘要直连)
GET /api/v1/market/info/600519         # 估值(PE/PB/总市值) + 最新价
GET /api/v1/market/freshness/coverage  # 数据覆盖矩阵（关注公司 × 数据类型，含定性覆盖维度：是否已索引年报正文 mda/risk）
GET /api/v1/market/ratios/600519       # 财务比率（毛利率/净利率等，最近3期）
GET /api/v1/market/ratios/600519/valuation-percentile  # A股 PE/PB 历史分位
```

> 行情/财务采集链：PG 缓存优先，未命中走 akshare 子进程（Tencent/Sina/Eastmoney），可配云端 MCP 兜底（`AKSHARE_CLOUD_MCP_URL`）。

---

### 4.4 文档中心 `/documents`

功能:上传PDF/报告,自动解析、切块、生成向量索引到知识库。

**使用流程**:
1. 进入文档中心,上传PDF文件(最大50MB,支持PDF/TXT/MD)
2. 上传接口**立即返回(202)**,由后台任务异步执行:解析PDF → 文本切片(默认512字符,64重叠) → BGE-M3向量化(1024维) → 存入Qdrant;用 `GET /documents/{id}/status` 轮询进度
3. 文档出现在列表中,可查看解析状态和切片数量
4. **财报类 PDF 表格自动结构化**: 按词坐标重建为 Markdown 表格,保留「集团/母公司」等列组表头,整块入库
5. 文档内容进入知识库,可被RAG搜索与问答

**上传时可选参数**: `title`(标题)、`doc_type`(类型:pdf/markdown/text/report等)、`company_id`(关联公司,从公司页上传会自动带上)
**关联公司**: 文档列表「🔗 关联公司」可随时关联/改绑/解除 (`PATCH /documents/{id}`)

**相关页面**: `/documents`

---

### 4.5 知识中心（后端 RAG 能力）

功能:混合RAG搜索 — 结合向量相似度 + BM25关键词搜索 + RRF 融合排序。

> **注意**: 由于 Embedding 当前配置走 Ollama 本地 API，若 Ollama 版本过旧(<0.3.0)可能返回零向量，此时稠密检索会失效。系统自动降级为稀疏检索(BM25+RRF)，效果仍然可用。
>
> **2026-11-25 二次瘦身**：前端 Knowledge 页（`/knowledge`）已删除；知识库作为事实检查的证据来源与后端 API 继续保留。
>
> **2026-11-26 六次简化**：知识库问答已退役——`POST /knowledge/ask` 与 `GET /knowledge/llm/models` 端点及 LLM 适配器（`core/adapters/llm.py`、`core/llm_usage.py`）已删除。知识库仅作为 Screener 事实检查的证据来源。

**知识库在链路中的角色**: Screener 事实检查器（审计意见/诉讼）依赖知识库检索年报切片。知识库为空时这些检查会判 `not_found` → 运行判「数据不足」。

**API**:
```
GET /api/v1/knowledge/search?query=苹果的AI战略&limit=5
GET /api/v1/knowledge/search?query=...&content_type=mda   # 按切片内容类型过滤
GET /api/v1/knowledge/search/document/{document_id}?query=...  # 只搜索指定文档
```

> **content_type 内容类型过滤**（2026-10-14 起）：文档索引时按章节关键词给切片打标 `mda`（经营讨论）/ `risk`（风险因素）/ `notes`（附注）/ `announcement`（公告）/ `other`，定性研究可定向检索（如管理层展望只搜 `mda`）。历史索引的切片保持 `other`，重新索引后自动打标。

---

### 4.6 AI 能力（内嵌于各模块）

> **LLM 已全面退役**（2026-11-25 深判退役 + 2026-11-26 知识库问答退役）：AI 中心（2026-11-24）、知识库问答（2026-11-26）、`/api/v1/ai/usage`（2026-11-25）均已删除。系统全链路零 LLM，唯一 AI 依赖是文档索引的 Ollama Embedding。

### 共享组件

| 组件 | 用途 |
|------|------|
| StockSearch.vue | 可复用股票搜索下拉 (v-model, 300ms防抖, 键盘导航) |
| StockChart.vue | ECharts K 线图 (MA5/MA20/成交量/dataZoom) |
| CommandPalette.vue | ⌘K 全局命令面板 |
| Sidebar.vue | 侧边栏导航 |

### 类型系统

前端视图当前使用 `src/stores/api.ts` 中手写的 TypeScript 接口；OpenAPI 类型生成管线保留为按需工具（当前视图未引用生成的类型文件）：

```bash
# 从后端 OpenAPI 模式按需生成前端类型
cd frontend && npm run gen
# 生成: backend/scripts/generate_openapi.py → openapi.json → src/types/api.ts
```

---

### 4.7 调度中心 `/scheduler`

功能:手动触发定时任务、查看任务状态。

**定时任务** (需 `SCHEDULER_ENABLED=true` 才自动运行):
| 任务名 | 默认时间 | 功能 |
|--------|---------|------|
| `market_data_update` | 工作日2am | 更新市场数据 |

**手动触发**:
```
POST /api/v1/scheduler/run/market_data_update
```

**查看调度器状态**:
```
GET /api/v1/scheduler/status            # 调度器状态(运行中/停止)
```

### 4.8 智能选股 `/screener`（2026-10-24；2026-11-25 深判退役）

功能：预设标准库驱动的全市场选股，产出**Markdown 价值推荐清单（三段报告：量化筛选 → 事实检查 → 不推荐/存疑原因）**。预设是唯一运行入口（freeform 模式已删除）。运行链路零 LLM，单轮 ≤2 分钟。

**运行方式（预设模式）**：
1. 打开 `/screener`，多选预设（8 套内置：核心资产/高成长/深度价值/质量价值GARP/周期反转 + 金融价值/银行价值/保险价值，只读；首次进入默认勾选全部内置预设）
2. 选组合方式：union（命中任一）/ intersection（全部命中）/ flatten（合并规则）
3. 触发运行 → 报告中每只推荐股标注命中预设

**预设管理**：内置与自建预设均只读（2026-11-25 起预设只读化，规则改动走代码/种子脚本），前端可查看规则明细。

**页面功能**：
- **数据质量卡片**：最新财务期、7 个关键指标覆盖、行情覆盖、知识库文档数；缺数据/知识库为空直接告警。
- **定时任务卡片**：cron/预设/下次运行，可后台「立即运行定时选股」。
- **报告视图**：最新报告指针 `GET /api/v1/screener/latest-report`；报告为三段结构——量化筛选（数值 + 行业分位）→ 事实检查 → 不推荐/存疑原因（fact_checks not_found 项 + 缺数据项）；尾部附「较上一轮」轮次对比（新增/移出/连续推荐），预设标注证据分层 grade 徽标（verified/neutral/failed）与回测证据行。
- **历史运行**：按状态筛选；每行支持 报告/明细。
**运行明细**：逐只确定性判定结论（推荐/未通过/数据不足）、理由（量化命中 + fact_checks 结果）、行业、价格（「置信度」列已随 confidence 退役删除）。fact_checks 支持券商口径豁免：券商不适用现金覆盖等口径时返回 exempt（视同通过）而非 not_found。

**API**：
```
GET  /api/v1/screener/metrics              # 42 个标准化指标（估值/质量/因子/银行保险）
GET  /api/v1/screener/presets              # 预设列表（含内置，只读）
POST /api/v1/screener/runs                 # Body: {"mode": "presets", "pool": "all", "preset_ids": [...], "combine": "union"}
GET  /api/v1/screener/runs/{id}            # 运行详情（含逐只确定性判定，历史运行仍可查）
GET  /api/v1/screener/latest-report        # 最近一次 completed 运行的报告指针（404 优雅降级）
GET  /api/v1/screener/runs/{id}/report     # Markdown 报告
GET  /api/v1/screener/schedule              # 定时快照（cron/预设/下次运行）
POST /api/v1/screener/schedule/run          # 后台立即运行一轮定时选股
GET  /api/v1/screener/data-quality          # 财务期/指标覆盖/行情覆盖/知识库状态与告警
```

> **2026-11-25 已删除的端点**：`POST /runs/{id}/cancel`（运行取消）、`/runs/{id}/portfolio*` 与 `/portfolios/*`（组合/再平衡）、`/runs/{id}/performance*`（表现跟踪/快照）、`/backtests*`（回测交互路由——回测脚本 `backend/tools/run_backtest_queue.py` 直调纯函数）、`GET /runs/{id}/diff`（变化日报）、`GET /runs/{id}/export`（CSV 导出）、`POST /runs/{id}/watchlist`（自选推送）。

> 全流程约 ≤2 分钟（全市场快照 + 财务补采 + 事实检查确定性判定，无 LLM 调用）。报告落 `backend/screener/reports/`。
>
> **数据来源**：业绩报表（`stock_yjbb_em`）提供 ROE/毛利率/净利率/EPS/营收与净利同比；资产负债表与现金流（`stock_zcfz_em`/`stock_xjll_em`）提供规模、负债率与经营现金流；流动/速动比率与三项周转率来自东财 F10 主要指标（`RPT_F10_FINANCE_MAINFINADATA`）。缺失指标会在初筛前按需补采。
>
> ⚠️ **数据时效**：筛选基于最近入库的财务数据，报告概览会标注「财务数据截至 YYYYQn」。财务数据由 `financial_data_update` 在工作日 3:15 自动刷新；定时选股在工作日 16:30。也可随时用「数据质量」卡片或 `GET /api/v1/screener/data-quality` 检查覆盖与告警。
>
> ⚠️ **知识库**：含定性标准的预设依赖已索引文档。知识库为空时事实检查判 `not_found`，运行会稳定判为“数据不足”；纯量化预设不受影响。

---


## 五~九、后端开发详情

> 数据库/迁移/种子数据、AI 能力与 Embedding、API 参考、配置与 .env、MCP 工具等后端单侧内容已移至 **[`backend/README.md`](backend/README.md)**。

---

## 十、常见问题

### Q: 后端启动后立刻503错误
可能 Embedding 模型加载中。等待几秒重试。确认Docker容器健康:
```bash
docker compose -f docker/docker-compose.yml ps
```

### Q: A股数据无法获取
A 股采集走 akshare 子进程直连（无外部数据库依赖）。排查两点：
1. akshare 子进程 venv 存在且 `AKSHARE_MCP_DIR` 配置正确
2. 网络可访问 Tencent/Sina/Eastmoney 数据源
行情页可点公司详情「↻ 刷新」重新拉取；失败时看后端日志中 `[akshare]` 前缀的 warning（含各层失败原因）。
```bash
POST /api/v1/market/prices/AAPL/ingest?provider=yfinance
```

### Q: 前端页面空白
1. 检查后端: `curl http://localhost:8000/health`
2. 清除浏览器缓存(Ctrl+Shift+R)
3. 重启前端

### Q: 文档上传失败
- 检查 `backend/data/uploads` 目录是否存在
- 检查文件大小(最大50MB)
- 确认Qdrant服务运行中

### Q: SOCKS 代理环境变量干扰
如果你本地启用了 SOCKS 代理（如 Clash），本地 localhost 连接可能受影响:
- **后端正向**: 启动时加前缀: `ALL_PROXY= all_proxy= uvicorn ...`
- `.bashrc` 已添加 `export no_proxy="localhost,127.0.0.0/8,::1"`

### Q: 如何完全重置项目
```bash
# 1. 停止所有服务
docker compose -f docker/docker-compose.yml down -v
kill $(lsof -ti:5173) 2>/dev/null
kill $(lsof -ti:8000) 2>/dev/null

# 2. 重新安装前端依赖
cd frontend
rm -rf node_modules
npm install

# 3. 重新启动
docker compose -f docker/docker-compose.yml up -d
cd backend && PYTHONPATH=. alembic upgrade head && python scripts/seed_data.py
```

### Q: Docker镜像拉取失败
```bash
# 检查Docker代理配置
docker info | grep -i proxy

# 如需绕过代理拉取
docker pull pgvector/pgvector:pg16
```

### Q: 知识库搜索卡住 / HuggingFace 超时
国内网络无法访问 HuggingFace，解决方案:
1. 后端已默认离线模式 (`HF_HUB_OFFLINE=1`),模型从本地缓存加载
2. Reranker 模型默认禁用（搜索走 RRF 融合排序,效果足够）
3. Embedding 模型使用 Ollama 本地 BGE-M3

### Q: Embedding 报 Ollama 连接错误
```bash
# 确认Ollama已启动
ollama serve

# 如 embedding 模型未下载
ollama pull bge-m3
```

---

## 十一、价值筛选标准流程 (实践指南)

```
┌─────────────────────────────────────────────────────────────┐
│  1. 确保数据底座就绪                                        │
│     数据质量卡片或 GET /api/v1/screener/data-quality        │
│     （行情覆盖 / 财务期 / 知识库文档数）                    │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 运行筛选                                                │
│     POST /api/v1/screener/runs                              │
│     Body: {"mode": "presets", "preset_ids": [...],          │
│            "combine": "union"}                              │
│     （工作日 16:30 也会定时自动运行）                       │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 看报告与判定                                            │
│     报告落 backend/screener/reports/                        │
│     GET /api/v1/screener/latest-report 取最新报告指针       │
│     逐只确定性结论：推荐/未通过/数据不足（三段报告）        │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 跟踪                                                    │
│     历史运行表查看历轮报告；报告尾部含「较上一轮」对比      │
│     （公司中心已退役，自选维护功能随之删除）                │
└─────────────────────────────────────────────────────────────┘
```

---

## 十二、代码目录结构

```
ai_research_os/
├── backend/
│   ├── api/app.py             # FastAPI应用工厂,所有路由注册
│   ├── core/                  # 核心基础设施
│   │   ├── config.py          # Pydantic配置(所有.env项)
│   │   ├── database.py        # 异步SQLAlchemy引擎 + get_db/managed_session
│   │   ├── container.py       # DI容器(懒加载单例)
│   │   ├── base.py            # ORM Base + TimestampMixin/UUIDMixin
│   │   ├── interfaces.py      # Protocol 接口(Embedding/VectorStore/LLM/服务协议)
│   │   ├── exceptions.py      # 统一异常体系
│   │   ├── logging.py         # structlog配置
│   │   ├── scheduler.py       # APScheduler调度器(market_data/cleanup)
│   │   ├── scheduler_routes.py# 调度 API 路由
│   │   ├── market_sync.py     # 市场数据定时采集
│   │   ├── event_service.py / event_log.py / event_routes.py / event_cleanup.py
│   │   ├── task_manager.py    # 持久任务队列(Postgres+worker)
│   │   ├── security.py        # JWT工具(V1未启用,有意保留)
│   │   └── adapters/          # 外部服务适配器
│   │       ├── embedding.py   # BGE-M3嵌入(Ollama API)
│   │       ├── reranker.py    # BGE Reranker
│   │       ├── vector_store.py# Qdrant向量存储
│   │       ├── cache.py       # Redis缓存
│   │       ├── pdf_parser.py  # PyMuPDF解析
│   │   ├── company/               # 公司中心(已退役,仅剩 GET /companies 供文档关联下拉;表与ORM保留)
│   ├── market/                # 市场中心(service/+routes/子目录+domain/repositories/akshare_executor)
│   ├── document/              # 文档中心(含 content_classifier.py 内容打标 + table_extractor.py 表格结构化)
│   ├── knowledge/             # 知识中心(混合RAG,读写document表+Qdrant)
│   ├── screener/              # 智能选股(筛选/事实检查/报告,编排型模块,零LLM)
│   ├── alembic/versions/      # 数据库迁移脚本
│   ├── tests/                 # pytest(专用 airesearch_test 库)
│   └── scripts/               # 工具脚本(seed_data/ingest_financials/reembed等)
├── frontend/
│   └── src/
│       ├── main.ts            # 应用入口
│       ├── App.vue            # 根组件
│       ├── router/            # Vue Router 路由
│       ├── stores/api.ts      # TanStack VueQuery hooks(全部API调用集中于此)
│       ├── components/        # 共享组件(StockSearch/StockChart/CommandPalette等)
│       └── views/             # 4个页面视图
├── docker/
│   ├── docker-compose.yml     # 数据库基础设施(postgres/qdrant/redis)
│   ├── Dockerfile.backend
│   └── init.sql               # 8个schema初始化
├── start-dev.cmd              # Windows一键启动(依赖栈+后端+前端)
├── USAGE.md                   # 本文档
└── README.md
```

> 已删除模块（2026-11-24）：`research/`、`portfolio/`、`ai/`、`dashboard/` 及前端对应视图——数据库表保留，回捡 `git revert`。

---

## 十三、完整操作工作流 (Walkthrough)

以下从零开始的端到端操作流程，适用于新用户快速上手：

### Step 1 — 准备股票数据

> 公司中心已退役（2026-11-26），无需手动创建公司——股票池与数据来自市场中心采集（akshare 全市场快照）。

### Step 2 — 上传文档

**页面：** 底部导航 → 文档 → 上传文档

1. 选择 PDF 文件（支持最大 50MB）
2. 系统自动解析 → 切片 → 向量化索引到 Qdrant
3. 文档列表显示切片数量，确认索引完成

### Step 3 — 验证知识库（API）

**方式：** API 或 Swagger（http://localhost:8000/docs）——前端 Knowledge 页已随二次瘦身删除

- `GET /api/v1/knowledge/search?query=工商银行 净息差`
- 知识库是 Screener 事实检查的证据来源（也是知识库问答的语料）；文档中心上传/索引后即生效

### Step 4 — 查看行情

**页面：** 底部导航 → 行情

1. 在搜索框输入股票代码 `601398`（或 `AAPL` 等），回车
2. 查看 K 线图（日线数据）
3. 下方财务指标：ROE、净息差、不良率、拨备覆盖率等

### Step 5 — 运行智能选股（核心）

**页面：** 首页 `/` → 智能选股

1. 「数据质量」卡片确认行情/财务/知识库覆盖无告警
2. 预设模式：勾选预设（如 金融价值/深度价值）→ union → 触发运行
3. 等待 ≤2 分钟（快照 + 财务补采 + 事实检查确定性判定，无 LLM 调用），查看报告与逐只结论
4. 回测验证用脚本 `backend/tools/run_backtest_queue.py`（需 `BACKTEST_MYSQL_URL`，结果落 JSON）

### Step 6 — 跟踪与行动

- 历史运行表：报告/明细（逐只确定性判定）；报告尾部含「较上一轮」轮次对比

---

*本文档随项目迭代更新. 最后更新: 2026-11-26*
