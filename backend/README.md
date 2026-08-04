# AI Research OS — Backend

Python/FastAPI 后端。完整使用手册见根目录 [`USAGE.md`](../USAGE.md)。

## 技术栈

- **框架**: FastAPI + async SQLAlchemy + Pydantic v2
- **存储**: PostgreSQL（多 schema + pgvector）+ Qdrant（向量）+ Redis（缓存）
- **AI**: DeepSeek（OpenAI 兼容，本机默认）/ Ollama（本地 LLM + Embedding）
- **数据源**: akshare（A股，MySQL 镜像 + 子进程），yfinance（美股）
- **质量**: pytest 125 用例 + ruff + mypy + pre-commit

## 架构

7 个业务模块，依赖只向上：

```
Company → Market + Document → Knowledge(RAG) → AI → Research → Portfolio
```

各模块文件结构并不完全统一：

| 形态 | 模块 |
|------|------|
| 完整四层 `models → schemas → service → routes` | company, document, ai |
| `service/` + `routes/` 子目录拆分 | market（另含 domain/repositories/akshare_executor）、portfolio（2 服务） |
| 顶层多个 `*_service.py` | research（session/evidence/report/gather/thesis/timeline 6 服务） |
| 薄模块（仅 routes + service，无自有 models/schemas） | knowledge（读写 document 表 + Qdrant）、dashboard（跨模块聚合） |

服务通过 `core/container.py` DI 容器懒加载，路由经 `Depends(get_container)` 获取。

## 启动

```bash
# 方式一：开发脚本（推荐，内置代理清理）
./backend/run_dev.sh
# 等价于: cd backend && ALL_PROXY= all_proxy= no_proxy=... PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

# 方式二：Makefile
make dev-backend

# 方式三：直接 uvicorn（必须先进入 backend/ 目录）
cd backend && ALL_PROXY= all_proxy= PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

> **注意**：`run_dev.sh` 内含硬编码绝对路径（`/home/wsm/codes/ai_research_OS/backend`），换机器需改。必须从 `backend/` 目录启动（`UPLOAD_DIR=data/uploads` 为相对路径）。代理环境变量会干扰 httpx，需 `ALL_PROXY= all_proxy=` 前缀。

## 数据库（7 个 Schema）

PostgreSQL 用 schema 做模块隔离，初始化 SQL 见 `docker/init.sql`：

| Schema | 表 |
|--------|-----|
| `company` | companies, company_tags |
| `market` | stock_prices, financial_metrics, macro_indicators, data_freshness |
| `document` | documents, document_chunks |
| `research` | research_sessions, research_evidences, research_reports |
| `portfolio` | holdings, investment_journal |
| `ai` | prompt_templates, ai_workflows |
| `core` | event_log, task_records, morning_briefs, observations |

- `knowledge` / `dashboard` 无独立 schema：knowledge 复用 document 表 + Qdrant 向量，dashboard 跨 schema 聚合查询
- akshare 数据在外部 MySQL 镜像（非 PG），不进本库

### Event Log（审计追踪）

`core.event_log` 表，所有数据写操作记录（会话创建 / Thesis 变更 / 文档上传 / AI 调用等），Write-once 不可改删。

### 迁移

```bash
cd backend
PYTHONPATH=. alembic upgrade head                      # 升级
PYTHONPATH=. alembic revision --autogenerate -m "描述" # 新迁移
PYTHONPATH=. alembic downgrade -1                      # 回滚
PYTHONPATH=. alembic current / history                 # 查看
```

### 种子数据

```bash
PYTHONPATH=. python scripts/seed_data.py
```
导入 8 家公司 + 1 条 NVDA 研究会话 + 默认 AI 模板。

## API 约定

- 所有端点前缀 `/api/v1`，交互式文档见 http://localhost:8000/docs
- 异常统一走 `core/exceptions.py` → `api/app.py` 集中 handler，返回结构化 JSON：404 / 422 / 409 / 401 / 403 / 502 / 500
- 接口速查：直接看各模块 `routes.py`，或根目录 `USAGE.md`「功能模块详解」

## 配置与环境变量

配置定义在 `core/config.py`（pydantic-settings，读 `backend/.env`，大小写不敏感）。以下为**代码默认值**与本机 `.env` 覆盖：

| 分组 | 变量 | 代码默认 | 本机 .env |
|------|------|---------|-----------|
| 数据库 | `DATABASE_URL` | postgresql+asyncpg://airesearch:airesearch_dev@127.0.0.1:5432/airesearch | 同默认（localhost:5432） |
| 向量库 | `QDRANT_HOST` / `QDRANT_PORT` | 127.0.0.1 / 6333 | — |
| Embedding | `EMBEDDING_PROVIDER` | ollama | — |
| | `OLLAMA_EMBEDDING_MODEL` | nomic-embed-text | **bge-m3** |
| | `EMBEDDING_DIMENSION` | 1024 | — |
| LLM | `LLM_PROVIDER` | **ollama** | **openai** |
| | `OPENAI_BASE_URL` | https://api.openai.com/v1 | https://api.deepseek.com |
| | `OPENAI_MODEL` | gpt-4o | deepseek-v4-flash |
| | `OLLAMA_MODEL` | llama3.1:70b | qwen3.5-98k:latest（注释） |
| Redis | `REDIS_URL` | redis://127.0.0.1:6380/0 | — |
| 文档 | `UPLOAD_DIR` / `MAX_UPLOAD_SIZE_MB` | data/uploads / 50 | — |
| | `CHUNK_SIZE` / `CHUNK_OVERLAP` | 512 / 64 | — |
| 市场 | `AKSHARE_ENABLED` / `YFINANCE_ENABLED` | true / true | — |
| 外部数据源 | `AKSHARE_MCP_DIR` / `NEWSNOW_MCP_SERVER_PATH` | /home/wsm/codes/akshare_mcp 等 | 机器相关 |
| 调度器 | `SCHEDULER_ENABLED` | **true** | — |
| 安全 | `SECRET_KEY` | 每次启动随机生成 | — |

> **默认是 Ollama，本机跑 DeepSeek**：代码里 `LLM_PROVIDER` 默认 `ollama`，本机 `.env` 设为 `openai` + DeepSeek（`deepseek-v4-flash`）。`deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 停用。
> 完整变量清单见 `core/config.py`。

## AI 能力

| 功能 | 所需服务 |
|------|---------|
| 公司/行情浏览 | 无 |
| 文档索引 | Embedding 需 Ollama（`OLLAMA_EMBEDDING_MODEL`，本机 bge-m3） |
| 知识库搜索 | 无（纯向量 + BM25，无需 LLM） |
| 研究观点/晨报/摘要/问答/研究报告 | DeepSeek / Ollama / OpenAI |

Ollama 版本过旧（<0.3.0）时 `/api/embed` 不可用，Embedding 降级为 BM25 稀疏检索 + RRF 融合，功能不受影响。

## MCP 工具（可选）

公司创建/搜索等工具逻辑在 `backend/mcp_company/service.py`，直接调用后端服务函数；如需从外部 MCP 客户端调用，参考该模块接口自行包装。

## 后台任务

`core/task_manager.py`：PostgreSQL 持久化 `core.task_records` + worker 循环 + 自动重试 + `(type,key)` 去重 + 启动恢复。快速研究（`research/quick.py`）通过它后台跑 计划→搜集→报告 链，SSE 推流进度。

## 测试

```bash
make test        # pytest，专用 airesearch_test 库 + 隔离 Qdrant 集合
```
当前 **125 passed**。
