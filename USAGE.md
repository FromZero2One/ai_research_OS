# AI Research OS 使用手册

> **Research First, not AI First** — AI是研究流程中的能力,不是系统的中心。

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
│  PostgreSQL (pgvector)  ← 公司/研究/行情/财务│
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
│  DeepSeek (云端 OpenAI 兼容)  或 Ollama (本地)│
└──────────────────────────────────────────────┘
```

> **数据源说明**: A 股/港股数据经 akshare 子进程直连采集（无外部数据库依赖），统一落 PostgreSQL（`market` schema）；docker-compose 仅包含 PostgreSQL、Qdrant、Redis。

### 核心技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3, Vite, TypeScript, Element Plus, TanStack Vue Query, ECharts |
| 后端 | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic |
| 数据库 | PostgreSQL 16 (pgvector), Qdrant, Redis |
| AI | DeepSeek V4 Flash (默认) / Ollama 本地 (备选) / 任意 OpenAI 兼容 API |
| 文档处理 | PyMuPDF + pdfplumber（财报表格结构化）, BGE-M3 向量化, 后台异步索引 |
| 知识检索 | Qdrant 稠密 + BM25 稀疏 + RRF 融合 + BGE Reranker；文档问答（DeepSeek/Ollama 可切换） |
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

#### Step 5 — (可选) 配置 AI 服务

项目默认使用 **DeepSeek**（云端 API，OpenAI 兼容端点），无需本地模型。只需配置 `.env` 中的 API Key：

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-deepseek-api-key
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
# light tier（证据分类/事实抽取）也走云端（本机无 Ollama 时）
LLM_TIER_LIGHT_PROVIDER=openai
LLM_TIER_LIGHT_MODEL=deepseek-chat
```

> **注意**: 2026-10 实测 `deepseek-chat` 可用且分类评测 15/15 全对；模型以 DeepSeek 官方文档为准。

**备选方案: 使用 Ollama 本地模型**

如需完全本地运行：

```bash
# 启动 Ollama 服务
ollama serve

# 下载模型 (以 qwen3.5 为例)
ollama pull qwen3.5:latest

# 验证连接
curl http://127.0.0.1:11434/api/generate -d '{"model":"qwen3.5","prompt":"hi","stream":false}'
```

对应 `.env` 配置：

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3.5
OLLAMA_EMBEDDING_MODEL=bge-m3
```

**其他国产模型配置示例**:

```env
# 通义千问
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
OPENAI_MODEL=qwen-plus
OPENAI_API_KEY=sk-xxx

# Moonshot (Kimi)
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.moonshot.cn/v1
OPENAI_MODEL=moonshot-v1-8k
OPENAI_API_KEY=sk-xxx
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
make lint        # 代码检查 (ruff)
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

### 4.1 工作台 Dashboard

**访问地址**: http://localhost:5173

进入系统后的首页,自动展示面板:

| 模块 | 说明 |
|------|------|
| **研究提醒** | 超过14天未研究的自选股,按需研究程度排序 |
| **自选股行情** | 关注公司(is_active)的最新价格和涨跌 |
| **行情概览** | 自选公司最新价/涨跌幅/行业 |
| **最近研究** | 最近开展的投研会话,点击可继续 |

> **旧晨报已下线**（2026-10-14）：原"Morning Brief"新闻聚合卡已移除，将由"差异日报"（只报变化）替代——见 Roadmap。

---

### 4.2 公司中心 `/companies`

功能:管理和浏览投资研究标的。

**已入库公司** (Seed数据):
AAPL (Apple), AMZN (Amazon), GOOGL (Alphabet), MSFT (Microsoft), NVDA (NVIDIA), TSLA (Tesla), JPM (JPMorgan), BRK.B (Berkshire)

> 也可通过 API 添加更多公司，包括 A 股（如 601988 中国银行）。

**功能列表**:
- 浏览公司列表,支持按名称/ticker搜索、按行业/标签筛选
- 查看公司详细信息(描述、行业、员工数、官网、创建时间等)
- 给公司打标签 (tech/ai/ev/megacap/value等)
- 查看/更新公司的投资观点(Thesis): Bull/Bear/Neutral + 决策(buy/sell/hold/watch/pass)
- 公司工作区:聚合视图(Thesis+最近研究+证据统计)
- **比率与估值分位卡片**: 公司详情页展示财务比率(毛利率/净利率/ROE等)与 A 股 PE/PB 历史分位 (`GET /api/v1/market/ratios/{ticker}`、`GET /api/v1/market/ratios/{ticker}/valuation-percentile`)
- **关注/自选**: 自选已并入公司中心 — `is_active=true` 即自选。添加: `POST /api/v1/companies/watch`;移除: `PATCH /api/v1/companies/{id}` 设 `is_active=false`;优先级/目标价/理由挂在公司上 (`priority`/`target_price`/`reason`)

**相关页面**:
- `/companies` — 公司列表
- `/companies/[id]` — 公司详情页

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

### 4.5 知识中心 `/knowledge`

功能:混合RAG搜索 — 结合向量相似度 + BM25关键词搜索 + RRF 融合排序。

> **注意**: 由于 Embedding 当前配置走 Ollama 本地 API，若 Ollama 版本过旧(<0.3.0)可能返回零向量，此时稠密检索会失效。系统自动降级为稀疏检索(BM25+RRF)，效果仍然可用。

**使用流程**:
1. 确保文档中心已有已索引的文档
2. 在知识中心输入自然语言问题
3. 系统执行: 向量化查询 → Qdrant向量搜索 → BM25关键词搜索(中文停用词+查询扩展) → RRF融合 → BGE Reranker重排序 → 返回相关段落+来源(命中词高亮、表格渲染)

**文档问答**:
```
POST /api/v1/knowledge/ask
Body: {"question": "中国银行2025年净利润是多少", "top_k": 8, "provider": "default", "model": null}
```
- 默认使用 DeepSeek(`provider=default`),可切换本地 Ollama 模型
- `GET /api/v1/knowledge/llm/models` 列出默认模型与可用 Ollama 模型
- 回答带来源引用 [1][2],关键数字加粗并注明单位/口径

**API**:
```
GET /api/v1/knowledge/search?query=苹果的AI战略&limit=5
GET /api/v1/knowledge/search?query=...&content_type=mda   # 按切片内容类型过滤
GET /api/v1/knowledge/search/document/{document_id}?query=...  # 只搜索指定文档
```

> **content_type 内容类型过滤**（2026-10-14 起）：文档索引时按章节关键词给切片打标 `mda`（经营讨论）/ `risk`（风险因素）/ `notes`（附注）/ `announcement`（公告）/ `other`，定性研究可定向检索（如管理层展望只搜 `mda`）。历史索引的切片保持 `other`，重新索引后自动打标。

---

### 4.6 AI中心 `/ai`

功能:提示词模板管理、模板执行、Token 用量统计。

**核心能力**:
- **提示词模板**: 预定义的System+User Prompt模板,可变量替换,支持temperature/max_tokens配置
- **模板执行**: `POST /api/v1/ai/generate` 按模板+变量生成（知识中心的 `knowledge_ask` 模板覆盖机制也读这里的模板表）
- **Token 用量统计**: `GET /api/v1/ai/usage` 按模型汇总调用次数与输入/输出 tokens（进程级统计，服务重启清零）；系统页（/system）有实时展示卡片

> **AI 是能力不是中心**（2026-10-14 瘦身）：文本摘要/结构化提取已移除——与知识中心 RAG 问答、研究流程内嵌的 LLM 能力重叠；AI 工作流此前已移除。

**依赖**: 必须配置 DeepSeek (或 Ollama/OpenAI 兼容 API)

### 共享组件

| 组件 | 用途 |
|------|------|
| StockSearch.vue | 可复用股票搜索下拉 (v-model, 300ms防抖, 键盘导航, 5个视图共用) |
| StockChart.vue | ECharts K 线图 (MA5/MA20/成交量/dataZoom) |
| ReportCharts.vue | 报告可视化：证据方向分布饼图 + 财务指标多周期趋势线（数据来自 structured_facts） |
| CommandPalette.vue | ⌘K 全局命令面板 |
| Sidebar.vue | 侧边栏导航 |

### 类型系统

前端视图当前使用 `src/stores/api.ts` 中手写的 TypeScript 接口；OpenAPI 类型生成管线保留为按需工具（当前视图未引用生成的类型文件）：

```bash
# 从后端 OpenAPI 模式按需生成前端类型
cd frontend && npm run gen
# 生成: backend/scripts/generate_openapi.py → openapi.json → src/types/api.ts
```

**API示例**:
```bash
# 列出提示词模板
GET  /api/v1/ai/templates

# 创建提示词模板
POST /api/v1/ai/templates
Body: {"name": "research_summary", "system_prompt": "你是研究分析师", "user_prompt_template": "总结关于{company}的{topic}", "temperature": 0.7}

# 执行提示词模板
POST /api/v1/ai/generate
Body: {"prompt_name": "research_summary", "variables": {"company": "AAPL", "topic": "AI战略"}}

# Token 用量汇总（进程级统计，系统页有展示卡片）
GET /api/v1/ai/usage
```

---

### 4.7 研究中心 `/research` — 核心功能

功能:标准投研工作流,从问题提出到决策记录全流程管理。

**标准工作流**:
```
选择公司 → 提出研究问题 → 收集证据(Evidence) → 形成Thesis → 记录决策
```

**详细步骤**:

**Step 1 — 创建研究会话**
```
POST /api/v1/research/sessions
Body: {"company_id": "...", "question": "NVDA在AI芯片市场的竞争优势能持续多久?", "status": "draft"}
```

状态流转: `draft` → `researching` → `reviewing` → `completed`(界面显示为中文:草稿/研究中/评审中/已完成;决策显示为 买入/卖出/持有/关注/跳过)

**Step 2 — 收集证据 (Evidence)**

两种方式:
- **系统自动搜集** — `POST /api/v1/research/sessions/{id}/auto-gather` 自动从知识库搜索相关文档片段作为证据
- **手动添加** — `POST /api/v1/research/sessions/{id}/evidences` 手动输入网络研究、财报数据等

每条证据标记类型: `supporting` (支持) / `opposing` (反对) / `neutral` (中性)。类型由两级分类判定：先关键词初值，收集完成后再由 LLM 批量复核覆盖（证据卡上显示 🤖 AI分类 徽标；`EVIDENCE_CLASSIFIER` 开关控制）。

每条证据还带**论断性质** `content_nature`（证据卡徽标：🔢 定量 / 💬 定性）：数字论断引用 Market 接口数据或已核实事实，定性论断供报告内联引用回跳。

财报类文档证据会自动抽取**结构化事实**（structured_facts，只取原文数字，禁推算），报告生成时据此计算 **多周期比对（YoY/QoQ）** 并从财务指标库生成 **同业中位对比**（均显式标注为计算值）。研究详情页的"数据可视化"卡片用 ECharts 展示证据方向分布与指标趋势。

> **交叉验证（质检器）**：抽取出的结构化事实会与 Market 接口聚合值自动比对，偏差 ≥10% 时生成"口径差异"观察事件（System 页可见），提示复核合并/归母口径——结构化事实只做质检，不替代 Market 数据。

证据列表: `GET /api/v1/research/sessions/{id}/evidences`
删除证据: `DELETE /api/v1/research/evidences/{evidence_id}`

**Step 3 — 生成研究计划**
```
POST /api/v1/research/sessions/{id}/plan
Body: {"focus_areas": ["竞争格局", "财务数据", "估值"]}
```
获取计划: `GET /api/v1/research/sessions/{id}/plan`

> 创建会话（含一键研究）时可指定 `plan_type`: `initial`（首次覆盖）/ `earnings`（财报点评）/ `thesis_check`（论点检验）/ `industry`（行业对比）——命中预置模板则零 LLM 调用直接生成计划；留空则由 AI 根据问题自动生成。

**Step 4 — 形成观点 (Thesis)**

综合所有证据,给出投资观点:
- **Thesis** — 综合论述(文字)
- **Decision** — 决策方向: buy / sell / hold / watch / pass
- **Confidence** — 信心度 0.0~1.0

更新会话: `PATCH /api/v1/research/sessions/{id}`

**Step 5 — 生成报告(可选,需AI服务)**
```
POST /api/v1/research/sessions/{id}/generate-report
Body: {"report_type": "detailed"}

# 最终化(锁定证据和观点)
POST /api/v1/research/sessions/{id}/finalize
```

获取报告: `GET /api/v1/research/sessions/{id}/reports`
对比报告差异: `GET /api/v1/research/reports/{report_id}/diff`

> **报告双轨 + 引用回溯**（2026-10-14 起）：报告中的**定性论断**末尾带 `[ev:xxx]` 引用编号，前端渲染为「📎证据」可点击锚点——点击自动滚动到对应证据卡并高亮闪烁；**数字论断**只使用「已核实事实」或 Market 数据区块给出的数字并标注口径，报告 AI 不改写不推算。

**相关页面**:
- `/research` — 所有研究会话列表
- `/research/[id]` — 某个会话的详情和工作台
- `/research/quick` — 快速研究(AI辅助,SSE流式输出)
- `/research/timeline` — 研究时间线视图

---

### 4.8 投资组合 `/portfolio`

功能:自选列表（已并入公司中心）、持仓记录、投资日记。

**自选列表 (Watchlist — 已并入 Company)**:
自选 = `is_active=True` 的公司。关注/取消关注直接操作公司：
```
GET  /api/v1/companies?is_active=true          # 列出关注中的公司
POST /api/v1/companies/watch                   # 加入自选 Body: {"ticker": "AAPL", "name": "...", "priority": 1, "reason": "..."}
PATCH /api/v1/companies/{company_id}           # 取消关注: {"is_active": false}
```

股票状态标签: `normal`(正常,绿色) / `attention`(关注,橙色) / `need_research`(需研究,红色)
系统自动追踪距上次研究的天数，>14天标记 attention，>30天标记 need_research。

**持仓管理 (Holdings)**:
```
GET  /api/v1/portfolio/holdings                # 所有持仓
POST /api/v1/portfolio/holdings               # 记录持仓 Body: {"ticker": "AAPL", "shares": 100, "avg_cost_basis": 150.0}
PATCH /api/v1/portfolio/holdings/{holding_id} # 更新持仓(如增持)
POST /api/v1/portfolio/holdings/{holding_id}/close  # 平仓
```

**投资日记 (Journal)**:
```
GET  /api/v1/portfolio/journal                 # 日记列表
POST /api/v1/portfolio/journal                # 写日记 Body: {"entry_type": "idea", "ticker": "...", "title": "...", "content": "..."}
GET  /api/v1/portfolio/journal/{entry_id}     # 日记详情
```

> 持仓与投资日志当前仅有后端接口,前端页面待 V2(P&L 追踪)一并提供。

**相关页面**:
- `/portfolio` — 自选列表
- `/portfolio/journal` — 投资日记

---

### 4.9 调度中心 `/scheduler`

功能:手动触发定时任务、查看观察报告。

**定时任务** (需 `SCHEDULER_ENABLED=true` 才自动运行):
| 任务名 | 默认时间 | 功能 |
|--------|---------|------|
| `market_data_update` | 工作日2am | 更新市场数据 |
| `observation_cycle` | 工作日5:30am | 运行自选股观察周期,更新研究提醒 |

**手动触发**:
```
POST /api/v1/scheduler/run/market_data_update
POST /api/v1/scheduler/run/observation_cycle
```

**查看调度器状态和观察报告**:
```
GET /api/v1/scheduler/status            # 调度器状态(运行中/停止)
GET /api/v1/scheduler/observations      # 最近的观察报告列表
POST /api/v1/scheduler/observe          # 手动触发一次观察
```

### 4.10 智能选股 `/screener`（2026-10-22 v1.5）

功能：预设标准库驱动的全市场选股。两种模式：

**预设模式（推荐，零 LLM 翻译，结果可复现）**：
1. 打开 `/screener`，触发区切换到「预设模式」
2. 多选预设（5 套内置：核心资产/高成长/深度价值/质量价值GARP/周期反转，也可自建；首次进入默认勾选全部内置预设）
3. 选组合方式：union（命中任一）/ intersection（全部命中）/ flatten（合并规则）
4. 触发运行 → 报告中每只推荐股标注命中预设

**自由文本模式（v1）**：维护自然语言选股标准 → LLM 翻译为规则 → 筛选。标准不变时规则缓存复用，零 LLM 调用。

**预设管理**：右侧「预设管理」抽屉——查看内置预设规则明细、新建/编辑/启停自建预设（内置只读）。

**API**：
```
GET  /api/v1/screener/metrics              # 18 个标准化指标（含营收/净利同比）
GET  /api/v1/screener/presets              # 预设列表（含内置）
POST /api/v1/screener/runs                 # Body: {"mode": "presets", "pool": "all", "preset_ids": [...], "combine": "union"}
GET  /api/v1/screener/runs/{id}            # 运行详情（含逐只判断）
GET  /api/v1/screener/runs/{id}/report     # Markdown 报告
GET  /api/v1/screener/runs/{id}/diff       # 变化日报（可加 ?base_run_id=... 指定任意基线）
POST /api/v1/screener/runs/{id}/cancel      # 取消进行中的筛选（阶段边界/逐只深判前生效）
GET  /api/v1/screener/runs/{id}/export      # 导出该轮判断为 CSV
GET  /api/v1/screener/schedule              # 定时快照（cron/预设/下次运行/Webhook 状态）
POST /api/v1/screener/schedule/run          # 后台立即运行一轮定时选股
POST /api/v1/screener/runs/{id}/portfolio   # 组合构建（Body 加 {"save": true, "name": "..."} 可保存）
GET  /api/v1/screener/runs/{id}/portfolios  # 某轮已保存组合
GET  /api/v1/screener/portfolios/{pid}      # 组合详情（DELETE 删除）
POST /api/v1/screener/portfolios/{pid}/rebalance # 按最新价计算漂移与买卖建议
POST /api/v1/screener/runs/{id}/performance/snapshot  # 记录当日表现快照（同日幂等）
GET  /api/v1/screener/runs/{id}/performance/history   # 历史表现快照
GET  /api/v1/screener/data-quality          # 财务期/指标覆盖/行情覆盖/知识库状态与告警
GET  /api/v1/screener/backtests             # 最近回测列表
POST /api/v1/screener/backtests             # 触发预设回测（Body: {"preset_id": "...", "years": 5}）
GET  /api/v1/screener/backtests/{id}        # 回测详情（含 split_sample）
GET  /api/v1/screener/backtests/{id}/report # 回测 Markdown 报告
POST /api/v1/screener/runs/{id}/to-research # 推荐股 → 研究中心会话（Body 可选 {"tickers": [...], "limit": 5}）
POST /api/v1/screener/runs/{id}/watchlist    # 推荐股 → 自选（Body 可选 {"tickers": [...], "limit": 50}）
```

> 全流程约 2-10 分钟（全市场快照 + 财务补采 + LLM 深判）。报告落 `backend/screener/reports/`。
>
> **数据来源**：业绩报表（`stock_yjbb_em`）提供 ROE/毛利率/净利率/EPS/营收与净利同比；资产负债表与现金流（`stock_zcfz_em`/`stock_xjll_em`）提供规模、负债率与经营现金流；流动/速动比率与三项周转率来自东财 F10 主要指标（`RPT_F10_FINANCE_MAINFINADATA`）。缺失指标会在初筛前按需补采。
>
> ⚠️ **数据时效**：筛选基于最近入库的财务数据。报告概览会标注「财务数据截至 YYYYQn」；自动更新调度尚未接入，长期未运行时注意报告期，或手动检查 `GET /api/v1/market/freshness/coverage`。

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

### Q: DeepSeek 返回空内容
- 确认 `.env` 中 `OPENAI_API_KEY` 已正确填写
- 确认 `OPENAI_BASE_URL` 和 `OPENAI_MODEL` 正确
- 本机默认配置为 `deepseek-chat`（OpenAI 兼容端点 `https://api.deepseek.com/v1`）
- 测试连接: `curl https://api.deepseek.com/chat/completions -H "Content-Type: application/json" -H "Authorization: Bearer sk-xxx" -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}]}'`

### Q: AI功能报Ollama连接错误
```bash
# 确认Ollama已启动
ollama serve

# 测试连接
curl http://127.0.0.1:11434/api/generate -d '{"model":"qwen3.5","prompt":"hi","stream":false}'

# 如模型未下载
ollama pull qwen3.5
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
如果你的系统设置了 `all_proxy=socks://127.0.0.1:7890/`,本地 localhost 连接可能受影响:
- **LLM**: 已通过 curl subprocess 绕过代理
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

### Q: DeepSeek 用哪个模型
本机当前配置 `deepseek-chat`（2026-10-13 实测可用，证据分类评测 15/15 全对）。模型上下架以 DeepSeek 官方为准；若需更强推理可换 `deepseek-reasoner`。

### Q: 如何切换到其他国产大模型
项目支持所有 OpenAI 兼容 API，修改 `.env` 中的以下三项即可:
```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=<你的API地址>
OPENAI_MODEL=<模型名>
OPENAI_API_KEY=<你的Key>
```

---

## 十一、投研标准流程 (实践指南)

```
┌─────────────────────────────────────────────────────────────┐
│  1. 发现机会                                               │
│     例: 看到NVDA财报超预期,想深入研究是否值得加仓           │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 创建研究会话                                           │
│     POST /api/v1/research/sessions                         │
│     Body: {"company_id": "NVDA公司ID", "question": "..."}  │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 收集证据                                               │
│     a) POST /api/v1/research/sessions/{id}/auto-gather     │
│        → AI从知识库自动搜索相关文档片段作为证据              │
│     b) POST /api/v1/research/sessions/{id}/evidences        │
│        → 手动输入财报数据/逻辑推理等                         │
│     c) 证据标记: supporting / opposing / neutral           │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 生成研究计划                                           │
│     POST /api/v1/research/sessions/{id}/plan               │
│     Body: {"focus_areas": ["竞争格局", "财务", "估值"]}     │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  5. 得出观点,更新会话                                      │
│     PATCH /api/v1/research/sessions/{id}                   │
│     Body: {"thesis": "...", "decision": "buy",             │
│            "confidence": 0.75, "status": "completed"}      │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  6. (可选) 生成研究报告                                    │
│     POST /api/v1/research/sessions/{id}/generate-report    │
└─────────────────────────┬───────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  7. 关联Portfolio                                         │
│     → 自选股添加thesis + 设置研究提醒                      │
│     → 投资日记记录决策理由                                 │
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
│   │   ├── scheduler.py       # APScheduler调度器(market_data/observation/cleanup)
│   │   ├── scheduler_routes.py# 调度/观察 API 路由
│   │   ├── market_sync.py     # 市场数据定时采集
│   │   ├── observation.py     # 观察记录模型
│   │   ├── observation_engine.py # 自选股观察引擎
│   │   ├── event_service.py / event_log.py / event_routes.py / event_cleanup.py
│   │   ├── task_manager.py    # 持久任务队列(Postgres+worker)
│   │   ├── llm_usage.py       # LLM token 用量累计器
│   │   ├── shared_queries.py  # 跨模块批量查询(dashboard取数管道)
│   │   ├── security.py        # JWT工具(V1未启用,有意保留)
│   │   └── adapters/          # 外部服务适配器
│   │       ├── llm.py         # DeepSeek(OpenAI兼容)/Ollama适配器,分级路由
│   │       ├── embedding.py   # BGE-M3嵌入(Ollama API)
│   │       ├── reranker.py    # BGE Reranker
│   │       ├── vector_store.py# Qdrant向量存储
│   │       ├── cache.py       # Redis缓存
│   │       ├── pdf_parser.py  # PyMuPDF解析
│   │       └── newsnow_mcp.py # NewsNow MCP 新闻源
│   ├── company/               # 公司中心(CRUD/标签/Thesis/自选is_active)
│   ├── market/                # 市场中心(service/+routes/子目录+domain/repositories/akshare_executor)
│   ├── document/              # 文档中心(含 content_classifier.py 内容打标 + table_extractor.py 表格结构化)
│   ├── knowledge/             # 知识中心(混合RAG,读写document表+Qdrant)
│   ├── ai/                    # AI中心(prompt模板CRUD+执行+token用量)
│   ├── research/              # 研究中心
│   │   ├── session_service.py / planner.py / gather_service.py / evidence_service.py
│   │   ├── report_service.py / thesis_service.py / timeline_service.py
│   │   ├── fact_validator.py  # structured_facts vs Market 交叉验证(纯函数)
│   │   ├── period_compare.py  # YoY/QoQ/同业比对(纯函数)
│   │   └── quick.py           # 一键快速研究(SSE流式)
│   ├── portfolio/             # 投资组合(持仓/日志,后端)
│   ├── dashboard/             # 仪表盘聚合(自选/提醒/行情概览/最近研究)
│   ├── alembic/versions/      # 数据库迁移脚本
│   ├── tests/                 # pytest(14个测试文件,专用 airesearch_test 库)
│   └── scripts/               # 工具脚本(seed_data/ingest_financials/reembed等)
├── frontend/
│   └── src/
│       ├── main.ts            # 应用入口
│       ├── App.vue            # 根组件
│       ├── router/            # Vue Router 路由
│       ├── stores/api.ts      # TanStack VueQuery hooks(全部API调用集中于此)
│       ├── components/        # 共享组件(StockSearch/StockChart/ReportCharts/CommandPalette等)
│       └── views/             # 13个页面视图
├── docker/
│   ├── docker-compose.yml     # 数据库基础设施(postgres/qdrant/redis)
│   ├── Dockerfile.backend
│   └── init.sql               # 9个schema初始化
├── start-dev.cmd              # Windows一键启动(依赖栈+后端+前端)
├── USAGE.md                   # 本文档
└── README.md
```

---

## 十三、完整操作工作流 (Walkthrough)

以下从零开始的端到端操作流程，适用于新用户快速上手：

### Step 1 — 创建公司

**页面：** 底部导航 → 公司 → 新建公司

| 字段 | 说明 |
|------|------|
| 名称 | 工商银行 |
| Ticker | 601398 |
| 交易所 | SSE |
| 标签 | banking, state-owned, megacap, value |

### Step 2 — 上传文档

**页面：** 底部导航 → 文档 → 上传文档

1. 选择 PDF 文件（支持最大 50MB）
2. 系统自动解析 → 切片 → 向量化索引到 Qdrant
3. 文档列表显示切片数量，确认索引完成

### Step 3 — 知识库搜索验证

**页面：** 底部导航 → 知识库

- 输入关键词搜索（如 `工商银行 净息差`）
- 系统返回关联切片 + 命中高亮（AI 问答用"文档问答"功能）

### Step 4 — 查看行情

**页面：** 底部导航 → 行情

1. 在搜索框输入股票代码 `601398`（或 `AAPL` 等），回车
2. 查看 K 线图（日线数据）
3. 下方财务指标：ROE、净息差、不良率、拨备覆盖率等

### Step 5 — AI 中心模板管理

**页面：** 底部导航 → AI

- **浏览模板：** 系统预设的提示词模板列表
- **执行模板：** 点击执行 → 弹窗填写变量 → 发送到 AI
- **编辑模板：** 点击编辑 → 修改名称/内容 → 保存
- **删除模板：** 点击删除

### Step 6 — 研究会话（核心）

**页面：** 底部导航 → 研究 → 新建会话

**6.1 新建会话**

| 字段 | 说明 |
|------|------|
| 标题 | 工商银行深度研究 |
| 关联公司 | 选择已创建的公司 |
| 提问 | 对公司的投资价值分析问题 |

**6.2 研究计划**
- 系统自动拆分 3-6 个研究子问题
- 逐一展示计划列表，可手动调整

**6.3 搜集证据**
- 点击"搜集证据" → 自动搜索知识库 + 市场数据
- 返回支持/反对/中性的证据列表（含来源引用）
- 也可手动添加证据

**6.4 生成研究报告**
- 点击"生成报告" → AI 综合计划+证据生成完整研报
- 输出包含财务分析、行业对比、估值判断等

**6.5 完结会话**
- 选择投资决定：buy / sell / hold / watch / pass
- 填写置信度（0.0~1.0）

### Step 7 — 投资组合

**页面：** 底部导航 → 投资组合

**7.1 创建自选列表**
- 点击"+ 新建" → 填写列表名称（如"银行股"）→ 填写描述 → 创建
- 创建时可选择同时添加股票代码

**7.2 添加股票**
- 展开列表下的"+ 添加股票" → 输入代码 → 确认

**7.3 编辑/删除列表**
- 点列表右上角"编辑" → 修改名称/描述 → 保存
- 点"删除" → 确认后删除整个列表

**7.4 移除股票**
- 点股票标签上的 × 按钮 → 从列表中移除

**7.5 持仓记录（可选）**
- 点"+ 添加" → 填写代码、持股数量、平均成本 → 保存

### Step 8 — 工作台 Dashboard

**页面：** 首页 `/`

| 模块 | 说明 |
|------|------|
| 👁️ 关注列表 | 自选股最新行情、涨跌、研究状态 |
| ⏰ 研究提醒 | 超过 14 天未研究的股票标记 |
| 📋 最近研究 | 最近 5 条研究会话，点击可继续 |

---

*本文档随项目迭代更新. 最后更新: 2026-10-14*
