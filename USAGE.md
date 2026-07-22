# AI Research OS 使用手册

> **Research First, not AI First** — AI是研究流程中的能力,不是系统的中心。

---

## 一、项目架构

```
┌──────────────────────────────────────────────┐
│  前端: Next.js 15 (localhost:3000)           │
│  后端: FastAPI (localhost:8000)              │
│  API文档: localhost:8000/docs (Swagger UI)   │
└──────────────────────────────────────────────┘
              ↓
┌──────────────────────────────────────────────┐
│  PostgreSQL (pgvector)  ← 公司/研究/文档数据 │
│  Qdrant (向量数据库)    ← 知识库索引         │
│  Redis                 ← 缓存               │
│  akshare MySQL (外置)  ← A股实时数据          │
└──────────────────────────────────────────────┘
              ↓ AI能力
┌──────────────────────────────────────────────┐
│  Ollama (本地)  或  OpenAI (云端)            │
└──────────────────────────────────────────────┘
```

### 核心技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Next.js 15, React 19, TypeScript, Tailwind CSS 4, TanStack React Query |
| 后端 | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic |
| 数据库 | PostgreSQL 16 (pgvector), Qdrant, Redis |
| AI | Ollama (本地Llama) / OpenAI (GPT-4o) |
| 文档处理 | PyMuPDF, BGE-M3 向量化模型 |
| 基础设施 | Docker Compose |

---

## 二、服务启动与停止

### 启动顺序

#### Step 1 — 启动数据库基础设施

```powershell
cd E:\Project\ai_research_OS
docker compose -f docker/docker-compose.yml up -d
```

验证启动成功:
```powershell
docker compose -f docker/docker-compose.yml ps
```

应有3个容器: `airesearch-postgres` (healthy), `airesearch-qdrant` (healthy), `airesearch-redis` (healthy)

---

#### Step 2 — 启动后端

**方式一: 前台运行 (推荐,方便看日志)**
```powershell
cd E:\Project\ai_research_OS\backend
$env:PYTHONPATH = "E:\Project\ai_research_OS\backend"
uvicorn api.app:app --host 0.0.0.0 --port 8000
```

**方式二: 后台运行**
```powershell
$env:PYTHONPATH = "E:\Project\ai_research_OS\backend"
Start-Process -FilePath "python" -ArgumentList "-m","uvicorn","api.app:app","--host","0.0.0.0","--port","8000" -WorkingDirectory "E:\Project\ai_research_OS\backend" -NoNewWindow -PassThru
```

> **启动时行为**: 后端启动会依次执行:
> 1. 连接PostgreSQL验证
> 2. 预热Embedding模型(BGE-M3,在后台加载,不阻塞启动)
> 3. 启动Scheduler(如已启用)

---

#### Step 3 — 启动前端

**方式一: 前台运行**
```powershell
cd E:\Project\ai_research_OS\frontend
npm run dev
```

**方式二: 后台运行**
```powershell
Start-Process -FilePath "E:\Program Files\nodejs\npm.cmd" -ArgumentList "run","dev" -WorkingDirectory "E:\Project\ai_research_OS\frontend" -NoNewWindow -PassThru
```

---

#### Step 4 — (可选) 启动 Ollama

**以下功能需要Ollama**: AI生成研究观点、文档摘要、知识库答案、快速研究、Morning Brief

下载安装: https://ollama.com

```powershell
# 启动Ollama服务
ollama serve

# 首次使用需要下载模型 (约40GB)
ollama pull llama3.1:70b
```

**常用Ollama命令:**
```powershell
ollama list              # 查看已下载模型
ollama ps                # 查看运行中的模型
ollama rm llama3.1:70b   # 删除模型
```

**备选方案: 使用 OpenAI**

编辑 `backend/.env`:
```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o
```

---

### 停止服务

```powershell
# 停止后端Python进程
Get-Process -Name python | Stop-Process

# 停止前端Node进程
Get-Process -Name node | Stop-Process

# 停止所有数据库容器
docker compose -f docker/docker-compose.yml down

# 停止并清除数据卷 (完全重置)
docker compose -f docker/docker-compose.yml down -v
```

---

### 快速启动脚本 (Makefile)

项目根目录提供了Makefile快捷命令:

```powershell
make dev        # 启动DB + 迁移 + 后端 (前端需单独启动)
make dev-db     # 仅启动数据库
make dev-backend # 仅启动后端
make dev-frontend # 仅启动前端
make migrate    # 运行数据库迁移
make reset-db   # 删除并重建数据库
make lint       # 代码检查 (ruff)
make test       # 运行测试
make ingest-sample # 加载示例数据
```

> 注意: Windows下Makefile需安装make或使用Git Bash

---

## 三、访问地址

| 服务 | 地址 | 说明 |
|------|------|------|
| 前端首页 | http://localhost:3000 | 工作台/仪表盘 |
| 后端API | http://localhost:8000 |  |
| API文档 | http://localhost:8000/docs | Swagger UI (交互式) |
| ReDoc | http://localhost:8000/redoc | 替代文档 |
| Qdrant控制台 | http://localhost:6333 | 向量数据库管理 |
| PostgreSQL | localhost:5432 | 用户:airesearch, 密码:airesearch_dev |
| Redis | localhost:6380 | (端口6380映射到容器6379) |

---

## 四、功能模块详解

### 4.1 工作台 Dashboard

**访问地址**: http://localhost:3000

进入系统后的首页,自动展示4个面板:

| 模块 | 说明 |
|------|------|
| **Morning Brief** | AI生成的每日早晨简报,工作日6am自动生成(需Ollama) |
| **研究提醒** | 超过14天未研究的自选股,按需研究程度排序 |
| **自选股行情** | Watchlist中股票的最新价格和涨跌 |
| **最近研究** | 最近开展的投研会话,点击可继续 |

右侧5个快捷入口可快速进入各功能模块。

> **Morning Brief机制**: 由Scheduler调度,工作日6am自动运行。也可手动触发(见Scheduler端点)。

---

### 4.2 公司中心 `/companies`

功能:管理和浏览投资研究标的。

**已入库公司** (Seed数据):
AAPL (Apple), AMZN (Amazon), GOOGL (Alphabet), MSFT (Microsoft), NVDA (NVIDIA), TSLA (Tesla), JPM (JPMorgan), BRK.B (Berkshire)

**功能列表**:
- 浏览公司列表,支持按名称/ticker搜索、按行业/标签筛选
- 查看公司详细信息(描述、行业、员工数、官网、创建时间等)
- 给公司打标签 (tech/ai/ev/megacap/value等)
- 查看/更新公司的投资观点(Thesis): Bull/Bear/Neutral + 决策(buy/sell/hold/watch)
- 公司工作区:聚合视图(Thesis+最近研究+证据统计)

**相关页面**:
- `/companies` — 公司列表
- `/companies/[id]` — 公司详情页

---

### 4.3 市场中心 `/market`

功能:查询股票行情和财务数据。

**A股数据** (6位数字代码,如 `600519` 茅台):

直接查询(需akshare MySQL连接,当前未连接):
```
GET /api/v1/market/prices/600519       # 日K线数据
GET /api/v1/market/search?query=茅台    # 搜索A股
GET /api/v1/market/financials/600519   # 财务指标(EPS/营收/ROE等)
GET /api/v1/market/info/600519         # 估值(PE/PB/PS等) + 最新价
GET /api/v1/market/symbols             # 列出所有可查询的A股代码
```

**美股数据** (字母代码,如 `AAPL`):

需要先采集数据到本地数据库:
```
POST /api/v1/market/prices/AAPL/ingest?provider=yfinance  # 采集1年数据到PG
GET  /api/v1/market/prices/AAPL                            # 查询采集的数据
```

**注意**: 当前akshare MySQL未连接,A股数据暂不可用。美股yfinance采集需要网络畅通。

---

### 4.4 文档中心 `/documents`

功能:上传PDF/报告,自动解析、切块、生成向量索引到知识库。

**使用流程**:
1. 进入文档中心,上传PDF文件(最大50MB,支持PDF/TXT/MD)
2. 系统自动处理:解析PDF → 文本切片(chunk默认512字符,64重叠) → BGE-M3向量化(1024维) → 存入Qdrant
3. 文档出现在列表中,可查看解析状态和切片数量
4. 文档内容进入知识库,可被RAG搜索

**上传时可选参数**: `title`(标题)、`doc_type`(类型:report/transcript/article/other)、`company_id`(关联公司)

**相关页面**: `/documents`

---

### 4.5 知识中心 `/knowledge`

功能:混合RAG搜索 — 结合向量相似度 + BM25关键词搜索 + Cross-encoder重排序。

**使用流程**:
1. 确保文档中心已有已索引的文档
2. 在知识中心输入自然语言问题
3. 系统执行:向量化查询 → Qdrant向量搜索 → BM25关键词搜索 → RRF融合 → Cross-encoder重排序 → 返回相关段落+来源

**API**:
```
GET /api/v1/knowledge/search?query=苹果的AI战略&limit=5&rerank=true
GET /api/v1/knowledge/search/document/{document_id}?query=...  # 只搜索指定文档
```

---

### 4.6 AI中心 `/ai`

功能:LLM编排、提示词模板管理、文本摘要和结构化信息提取。

**核心能力**:
- **提示词模板**: 预定义的System+User Prompt模板,可变量替换,支持temperature/max_tokens配置
- **文本摘要**: 对任意文本生成指定长度摘要
- **结构化提取**: 从文本中按JSON Schema提取结构化数据
- **AI工作流**: 串联多个LLM步骤(V2支持LangGraph DAG)

**依赖**: 必须运行Ollama或配置OpenAI API Key

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

# 文本摘要
POST /api/v1/ai/summarize
Body: {"text": "很长的文档内容...", "max_length": 200, "format": "paragraph"}

# 结构化提取
POST /api/v1/ai/extract
Body: {"text": "Apple Q2 revenue $90.1B, up 4%", "schema": {"revenue": "number", "quarter": "string"}}

# 创建AI工作流
POST /api/v1/ai/workflows
Body: {"name": "research_pipeline", "steps": [{"type": "llm", "name": "分析", "system": "...", "prompt": "..."}]}

# 执行工作流
POST /api/v1/ai/workflows/{workflow_id}/execute
Body: {"input_data": {"company": "AAPL"}}
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

状态流转: `draft` → `researching` → `completed`

**Step 2 — 收集证据 (Evidence)**

两种方式:
- **系统自动搜集** — `POST /api/v1/research/sessions/{id}/auto-gather` 自动从知识库搜索相关文档片段作为证据
- **手动添加** — `POST /api/v1/research/sessions/{id}/evidences` 手动输入网络研究、财报数据等

每条证据标记类型: `supporting` (支持) / `opposing` (反对) / `neutral` (中性)

证据列表: `GET /api/v1/research/sessions/{id}/evidences`
删除证据: `DELETE /api/v1/research/evidences/{evidence_id}`

**Step 3 — 生成研究计划**

```
POST /api/v1/research/sessions/{id}/plan
Body: {"focus_areas": ["竞争格局", "财务数据", "估值"]}
```

获取计划: `GET /api/v1/research/sessions/{id}/plan`

**Step 4 — 形成观点 (Thesis)**

综合所有证据,给出投资观点:
- **Thesis** — 综合论述(文字)
- **Decision** — 决策方向: buy / sell / hold / watch / pass
- **Confidence** — 信心度 0.0~1.0

更新会话: `PATCH /api/v1/research/sessions/{id}`

**Step 5 — 生成报告(可选,需Ollama)**

```
POST /api/v1/research/sessions/{id}/generate-report
Body: {"report_type": "detailed"}

# 最终化(锁定证据和观点)
POST /api/v1/research/sessions/{id}/finalize
```

获取报告: `POST /api/v1/research/sessions/{id}/reports`
对比报告差异: `GET /api/v1/research/reports/{report_id}/diff`

**相关页面**:
- `/research` — 所有研究会话列表
- `/research/[id]` — 某个会话的详情和工作台
- `/research/quick` — 快速研究(AI辅助,SSE流式输出)
- `/research/timeline` — 研究时间线视图

---

### 4.8 投资组合 `/portfolio`

功能:管理自选股、持仓记录、投资日记。

**自选股列表 (Watchlist)**:
```
GET  /api/v1/portfolio/watchlists              # 列出所有自选股列表
POST /api/v1/portfolio/watchlists             # 创建自选股列表 Body: {"name": "科技股", "description": "..."}
GET  /api/v1/portfolio/watchlists/{watchlist_id}  # 某个列表详情
DELETE /api/v1/portfolio/watchlists/{watchlist_id} # 删除列表

POST /api/v1/portfolio/watchlists/{watchlist_id}/items  # 添加股票到列表
Body: {"company_id": "...", "ticker": "AAPL", "priority": 1, "thesis": "生态壁垒高"}
DELETE /api/v1/portfolio/watchlists/items/{item_id}    # 从列表移除
```

股票状态标签: `normal`(正常,绿色) / `attention`(关注,橙色) / `need_research`(需研究,红色)
系统自动追踪距上次研究的天数

**持仓管理 (Holdings)**:
```
GET  /api/v1/portfolio/holdings                # 所有持仓
POST /api/v1/portfolio/holdings               # 记录持仓 Body: {"company_id": "...", "quantity": 100, "avg_cost": 150.0}
PATCH /api/v1/portfolio/holdings/{holding_id} # 更新持仓(如增持)
POST /api/v1/portfolio/holdings/{holding_id}/close  # 平仓
```

**投资日记 (Journal)**:
```
GET  /api/v1/portfolio/journal                 # 日记列表
POST /api/v1/portfolio/journal                # 写日记 Body: {"title": "...", "content": "...", "company_id": "...", "session_id": "..."}
GET  /api/v1/portfolio/journal/{entry_id}     # 日记详情
```

**相关页面**:
- `/portfolio` — 总览
- `/portfolio/watchlists` — 管理自选股列表
- `/portfolio/journal` — 投资日记

---

### 4.9 调度中心 `/scheduler`

功能:手动触发定时任务、查看观察报告。

**定时任务** (需 `SCHEDULER_ENABLED=true` 才自动运行):
| 任务名 | 默认时间 | 功能 |
|--------|---------|------|
| `market_data_update` | 工作日2am | 更新市场数据 |
| `morning_brief` | 工作日6am | 生成Morning Brief |
| `observation_cycle` | 工作日5:30am | 运行自选股观察周期,更新研究提醒 |

**手动触发**:
```
POST /api/v1/scheduler/run/market_data_update
POST /api/v1/scheduler/run/morning_brief
POST /api/v1/scheduler/run/observation_cycle
```

**查看调度器状态和观察报告**:
```
GET /api/v1/scheduler/status            # 调度器状态(运行中/停止)
GET /api/v1/scheduler/observations      # 最近的观察报告列表
POST /api/v1/scheduler/observe          # 手动触发一次观察
```

---

## 五、数据库与数据

### 数据库架构 (9个Schema)

项目使用PostgreSQL的Schema功能做模块隔离:

| Schema | 说明 |
|--------|------|
| `company` | 公司信息、标签、Thesis |
| `market` | 行情数据、财务指标 |
| `document` | 文档和切片 |
| `knowledge` | 知识库元数据 |
| `ai` | AI模板和工作流 |
| `research` | 研究会话、证据、报告 |
| `portfolio` | 自选股、持仓、日记 |
| `dashboard` | 聚合数据(已废弃,直接查询) |
| `event_log` | 审计日志,所有写操作的记录追踪 |

初始化SQL: `docker/init.sql`

### Event Log (审计追踪)

所有数据写操作都会记录到 `event_log` 表,包括:
- 研究会话创建/更新/完成
- Thesis变更
- 文档上传/索引
- AI调用记录
- LLM使用量统计

这是Write-once审计日志,不可修改删除。

### 数据库迁移

```powershell
cd E:\Project\ai_research_OS\backend
$env:PYTHONPATH = "E:\Project\ai_research_OS\backend"

alembic upgrade head          # 升级到最新
alembic revision --autogenerate -m "描述"  # 创建新迁移
alembic downgrade -1           # 回滚一个版本
alembic current               # 查看当前版本
alembic history               # 查看迁移历史
```

### 种子数据

项目启动时运行了`scripts/seed_data.py`,已导入:
- 8家美股公司(AAPL/AMZN/GOOGL/MSFT/NVDA/TSLA/JPM/BRK.B)
- 1条NVDA研究会话(draft状态): "NVDA — AI Growth Thesis 2026"
- 默认AI提示词模板

重新seed:
```powershell
cd E:\Project\ai_research_OS\backend
$env:PYTHONPATH = "E:\Project\ai_research_OS\backend"
python scripts/seed_data.py
```

---

## 六、AI能力说明

### 什么时候需要 Ollama/OpenAI

| 功能 | 所需服务 |
|------|---------|
| 公司浏览、搜索 | 无 |
| 市场行情(K线) | 无(数据源决定) |
| 文档上传/解析/索引 | 无(纯本地处理,BGE-M3) |
| 知识库搜索 | 无(向量+BM25搜索,无需LLM) |
| **AI生成研究观点** | Ollama 或 OpenAI |
| **AI生成Morning Brief** | Ollama 或 OpenAI |
| **文档摘要** | Ollama 或 OpenAI |
| **知识库答案摘要** | Ollama 或 OpenAI |
| **快速研究(AI辅助)** | Ollama 或 OpenAI |
| **研究计划生成** | Ollama 或 OpenAI |
| **研究报告生成** | Ollama 或 OpenAI |

### Embedding模型

文档索引使用 **BGE-M3** (多语言 embedding 模型,1024维),首次查询时懒加载。
Ollama也提供 `OLLAMA_EMBEDDING_MODEL=nomic-embed-text` 选项,但默认使用BGE-M3。

---

## 七、API参考

完整API文档: http://localhost:8000/docs

> **注意**: 所有端点前缀为 `/api/v1`,下面表格省略该前缀。

### Health
| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 服务健康检查 |

### Companies
| 端点 | 方法 | 说明 |
|------|------|------|
| `/companies` | GET, POST | 列出/创建公司 |
| `/companies/{company_id}` | GET, PATCH, DELETE | 获取/更新/删除公司 |
| `/companies/by-ticker/{ticker}/thesis` | GET, POST | 获取/设置公司Thesis |
| `/companies/by-ticker/{ticker}/workspace` | GET | 公司聚合视图(Thesis+研究+证据) |

### Market
| 端点 | 方法 | 说明 |
|------|------|------|
| `/market/prices/{ticker}` | GET | K线数据 |
| `/market/prices/{ticker}/ingest` | POST | 采集数据到本地 |
| `/market/search` | GET | 搜索A股 |
| `/market/info/{ticker}` | GET | 股票信息+估值 |
| `/market/financials/{ticker}` | GET | 财务指标 |
| `/market/symbols` | GET | 列出可查询的A股代码 |

### Documents
| 端点 | 方法 | 说明 |
|------|------|------|
| `/documents` | GET | 文档列表 |
| `/documents/upload` | POST | 上传文档(自动索引) |
| `/documents/{document_id}` | GET, DELETE | 获取/删除文档 |

### Knowledge
| 端点 | 方法 | 说明 |
|------|------|------|
| `/knowledge/search` | GET | 混合RAG搜索 |
| `/knowledge/search/document/{document_id}` | GET | 在指定文档中搜索 |

### AI
| 端点 | 方法 | 说明 |
|------|------|------|
| `/ai/templates` | GET, POST | 列出/创建提示词模板 |
| `/ai/templates/{template_id}` | GET | 获取模板详情 |
| `/ai/generate` | POST | 执行提示词 |
| `/ai/summarize` | POST | 文本摘要 |
| `/ai/extract` | POST | 结构化提取 |
| `/ai/workflows` | POST | 创建AI工作流 |
| `/ai/workflows/{workflow_id}/execute` | POST | 执行工作流 |

### Research
| 端点 | 方法 | 说明 |
|------|------|------|
| `/research/sessions` | GET, POST | 列出/创建研究会话 |
| `/research/sessions/{session_id}` | GET, PATCH, DELETE | 获取/更新/删除会话 |
| `/research/sessions/{session_id}/evidences` | GET, POST | 列出/添加证据 |
| `/research/evidences/{evidence_id}` | DELETE | 删除证据 |
| `/research/sessions/{session_id}/auto-gather` | POST | 自动从知识库搜集证据 |
| `/research/sessions/{session_id}/plan` | GET, POST | 获取/创建研究计划 |
| `/research/sessions/{session_id}/reports` | GET, POST | 获取/生成报告 |
| `/research/reports/{report_id}/diff` | GET | 报告差异对比 |
| `/research/sessions/{session_id}/finalize` | POST | 最终化(锁定证据和观点) |
| `/research/sessions/{session_id}/timeline` | GET | 会话时间线 |
| `/research/quick` | POST | 快速研究(AI辅助,SSE流式) |
| `/research/quick/{session_id}/stream` | GET | 快速研究SSE流 |
| `/research/quick/{session_id}/status` | GET | 快速研究状态查询 |
| `/research/timeline` | GET | 全局研究时间线 |

### Portfolio
| 端点 | 方法 | 说明 |
|------|------|------|
| `/portfolio/watchlists` | GET, POST | 列出/创建自选股列表 |
| `/portfolio/watchlists/{watchlist_id}` | GET, DELETE | 获取/删除列表 |
| `/portfolio/watchlists/{watchlist_id}/items` | POST | 添加股票到列表 |
| `/portfolio/watchlists/items/{item_id}` | DELETE | 移除股票 |
| `/portfolio/holdings` | GET, POST | 持仓列表/记录持仓 |
| `/portfolio/holdings/{holding_id}` | PATCH | 更新持仓 |
| `/portfolio/holdings/{holding_id}/close` | POST | 平仓 |
| `/portfolio/journal` | GET, POST | 日记列表/写日记 |
| `/portfolio/journal/{entry_id}` | GET | 日记详情 |

### Dashboard
| 端点 | 方法 | 说明 |
|------|------|------|
| `/dashboard` | GET | 聚合数据(首页用的所有数据) |
| `/dashboard/brief` | GET | Morning Brief内容 |
| `/dashboard/watchlist` | GET | 自选股行情摘要 |

### Scheduler
| 端点 | 方法 | 说明 |
|------|------|------|
| `/scheduler/status` | GET | 调度器状态 |
| `/scheduler/run/{job_name}` | POST | 手动触发任务 |
| `/scheduler/observations` | GET | 观察报告列表 |
| `/scheduler/observe` | POST | 手动触发观察 |

---

## 八、配置与环境变量

项目配置文件: `backend/.env`

主要配置项:

```env
# 应用
APP_NAME="AI Research OS"
DEBUG=true
ENV=development

# 数据库
DATABASE_URL=postgresql+asyncpg://airesearch:airesearch_dev@localhost:5432/airesearch
DATABASE_ECHO=false              # 打印SQL日志(调试用)

# 向量数据库
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_PREFER_GRPC=true           # 优先gRPC(更快)

# Embedding
EMBEDDING_MODEL=BAAI/bge-m3       # 默认用sentence-transformers
EMBEDDING_DIMENSION=1024           # BGE-M3维度
EMBEDDING_DEVICE=cpu               # 或 cuda

# LLM (必须配置一个)
LLM_PROVIDER=ollama               # 或 openai
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:70b
OLLAMA_EMBEDDING_MODEL=nomic-embed-text
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o

# Redis
REDIS_URL=redis://localhost:6380/0   # 注意端口6380
REDIS_TTL=3600

# 文档处理
UPLOAD_DIR=data/uploads
MAX_UPLOAD_SIZE_MB=50
CHUNK_SIZE=512                      # 切片大小(字符数)
CHUNK_OVERLAP=64                    # 切片重叠

# 市场数据
AKSHARE_ENABLED=true               # A股akshare MySQL
YFINANCE_ENABLED=true              # 美股yfinance

# 调度器
SCHEDULER_ENABLED=false            # true=开启定时任务
MARKET_DATA_SCHEDULE="0 2 * * 1-5" # 工作日2am
REPORT_SCHEDULE="0 6 * * 1-5"      # 工作日6am
OBSERVATION_SCHEDULE="30 5 * * 1-5" # 工作日5:30am

# 安全
SECRET_KEY=dev-secret-key           # 生产环境必须改

# CORS
CORS_ORIGINS=["http://localhost:3000"]
```

---

## 九、MCP Server (可选扩展)

项目包含一个MCP (Model Context Protocol) 服务器,用于给AI工具提供公司数据访问能力。

路径: `mcp-company/server.py`

```powershell
cd E:\Project\ai_research_OS\mcp-company
python server.py
```

该服务器可被AI编码工具(如Cursor/Cline)调用,提供自然语言查询公司数据的能力。

---

## 十、常见问题

### Q: 后端启动后立刻503错误
可能Embedding模型下载中。等待几秒重试。确认Docker容器健康:
```powershell
docker compose -f docker/docker-compose.yml ps
```

### Q: A股数据无法获取
当前akshare MySQL数据源未连接(A股需要外部MySQL服务)。可用美股替代:
```powershell
# 采集美股数据
POST /api/v1/market/prices/AAPL/ingest?provider=yfinance
```

### Q: AI功能报Ollama连接错误
```powershell
# 确认Ollama已启动
ollama serve

# 测试连接
curl http://127.0.0.1:11434/api/generate -d "{\"model\":\"llama3.1:70b\",\"prompt\":\"hi\",\"stream\":false}"

# 如模型未下载
ollama pull llama3.1:70b
```

### Q: 前端页面空白
1. 检查后端: `python -c "import httpx; print(httpx.get('http://localhost:8000/health').text)"`
2. 清除浏览器缓存(Ctrl+Shift+R)
3. 重启前端

### Q: 文档上传失败
- 检查 `backend/data/uploads` 目录是否存在
- 检查文件大小(最大50MB)
- 确认Qdrant服务运行中

### Q: 如何完全重置项目
```powershell
# 1. 停止所有服务
Get-Process -Name python,node | Stop-Process
docker compose -f docker/docker-compose.yml down -v

# 2. 重新安装前端依赖
cd frontend
Remove-Item -Recurse -Force node_modules
npm install

# 3. 重新启动
docker compose -f docker/docker-compose.yml up -d
cd backend; alembic upgrade head; python scripts/seed_data.py
```

### Q: Docker镜像拉取失败
```powershell
# 检查Docker代理配置
docker system info | Select-String proxy

# 如需绕过代理拉取
docker pull pgvector/pgvector:pg16  # 直接拉取
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
│   ├── api/app.py           # FastAPI应用工厂,所有路由注册
│   ├── core/                 # 核心基础设施
│   │   ├── config.py         # Pydantic配置(所有.env项)
│   │   ├── database.py      # 异步SQLAlchemy引擎
│   │   ├── base.py          # ORM Base + TimestampMixin
│   │   ├── crud.py          # 通用CRUD
│   │   ├── security.py      # JWT/密码哈希
│   │   ├── logging.py       # structlog配置
│   │   ├── scheduler.py     # APScheduler调度器
│   │   ├── scheduler_jobs.py# 定时任务定义
│   │   ├── event_service.py # 事件记录
│   │   ├── event_log.py     # 审计日志模型
│   │   ├── observation_engine.py # 自选股观察引擎
│   │   └── adapters/        # 外部服务适配器
│   │       ├── llm.py       # Ollama/OpenAI适配器
│   │       ├── embedding.py # BGE-M3嵌入
│   │       ├── vector_store.py # Qdrant向量存储
│   │       ├── cache.py     # Redis缓存
│   │       └── akshare_mysql.py # A股MySQL
│   ├── company/              # 公司中心
│   ├── market/               # 市场中心
│   ├── document/             # 文档中心
│   ├── knowledge/            # 知识中心(RAG)
│   ├── ai/                   # AI中心
│   ├── research/             # 研究中心
│   │   ├── quick.py          # 快速研究(SSE)
│   │   └── timeline.py       # 时间线
│   ├── portfolio/            # 投资组合
│   ├── dashboard/            # 仪表盘聚合
│   ├── alembic/versions/     # 数据库迁移脚本
│   └── scripts/             # 工具脚本
│       ├── seed_data.py     # 种子数据
│       └── seed_market_data.py # 市场数据
├── frontend/
│   └── src/
│       ├── app/              # Next.js App Router页面
│       ├── components/       # 共享组件
│       └── lib/api.ts        # React Query hooks + API客户端
├── docker/
│   ├── docker-compose.yml   # 数据库基础设施
│   ├── Dockerfile.backend
│   └── init.sql             # 9个schema初始化
├── mcp-company/             # MCP服务器(可选)
├── docs/                    # 项目计划文档
├── USAGE.md                 # 本文档
└── README.md
```

---

*本文档随项目迭代更新. 最后更新: 2026-07-22*