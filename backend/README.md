# AI Research OS — Backend

Python/FastAPI 后端。完整使用手册见根目录 [`USAGE.md`](../USAGE.md)。

## 技术栈

- **框架**: FastAPI + async SQLAlchemy + Pydantic v2
- **存储**: PostgreSQL (pgvector, 多 schema) + Qdrant (向量) + Redis (缓存)
- **AI**: DeepSeek (OpenAI 兼容) / Ollama (Embedding BGE-M3)
- **数据源**: akshare (A股, MySQL 镜像 + 子进程), yfinance (美股)
- **质量**: pytest 125 用例 + ruff + mypy + pre-commit

## 架构

7 个业务模块，依赖只向上：

```
Company → Market + Document → Knowledge(RAG) → AI → Research → Portfolio
```

- `core/` — 基础设施（config/database/container/interfaces/adapters/后台任务/调度）
- `dashboard/` — 聚合查询
- 每个模块遵循 `models.py → schemas.py → service.py → routes.py`

服务通过 `core/container.py` DI 容器懒加载，路由经 `Depends(get_container)` 获取。

## 启动

```bash
# 依赖已装前提下（或 make dev-backend）
cd backend && ALL_PROXY= all_proxy= PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000
```

> 必须从 `backend/` 目录启动（`UPLOAD_DIR=data/uploads` 为相对路径）。代理环境变量会干扰 httpx，需 `ALL_PROXY= all_proxy=` 前缀。

## 数据库（9 个 Schema）

PostgreSQL 用 schema 做模块隔离，初始化 SQL 见 `docker/init.sql`：

| Schema | 说明 |
|--------|------|
| `company` | 公司信息、标签、Thesis |
| `market` | 行情数据、财务指标 |
| `document` | 文档和切片 |
| `knowledge` | 知识库元数据 |
| `ai` | AI模板和工作流 |
| `research` | 研究会话、证据、报告 |
| `portfolio` | 持仓、投资日记（自选已并入 company） |
| `akshare` | 外部 akshare MySQL 镜像同步的行情/财务数据 |
| `event_log` | 审计日志，所有写操作的记录追踪 |

### Event Log（审计追踪）

所有数据写操作写入 `event_log` 表（会话创建/Thesis 变更/文档上传/AI 调用等），Write-once 不可改删。

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

- 所有端点前缀 `/api/v1`，完整文档见 http://localhost:8000/docs
- 异常统一走 `core/exceptions.py` → `api/app.py` 集中 handler，返回结构化 JSON（404/422/409/401/403/502）
- 接口速查见根目录 `USAGE.md` 的「功能模块详解」，或直接看各模块 `routes.py`

## 配置与环境变量（backend/.env）

```env
# 数据库
DATABASE_URL=postgresql+asyncpg://airesearch:airesearch_dev@localhost:5432/airesearch
# 向量库
QDRANT_HOST=localhost
QDRANT_PORT=6333
# Embedding（Ollama BGE-M3, 1024维）
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=bge-m3
EMBEDDING_DIMENSION=1024
# LLM（默认 DeepSeek V4 Flash）
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash        # 或 deepseek-v4-pro
# Redis
REDIS_URL=redis://localhost:6380/0
# 文档处理
UPLOAD_DIR=data/uploads
MAX_UPLOAD_SIZE_MB=50
CHUNK_SIZE=512
# 市场数据
AKSHARE_ENABLED=true
YFINANCE_ENABLED=true
# 外部数据源（机器相关）
AKSHARE_MCP_DIR=/home/wsm/codes/akshare_mcp
AKSHARE_MYSQL_HOST=127.0.0.1
NEWSNOW_MCP_SERVER_PATH=/home/wsm/codes/newsnow/tools/mcp-server.ts
# 调度器
SCHEDULER_ENABLED=false
# 安全（单用户本地，无认证）
SECRET_KEY=dev-secret-key
# CORS
CORS_ORIGINS=["http://localhost:5173"]
```

> `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 停用，勿用。

## AI 能力

| 功能 | 所需服务 |
|------|---------|
| 公司/行情浏览 | 无 |
| 文档索引 | Embedding 需 Ollama（BGE-M3） |
| 知识库搜索 | 无（纯向量+BM25，无需 LLM） |
| 研究观点/晨报/摘要/问答/研究报告 | DeepSeek / Ollama / OpenAI |

Ollama 版本过旧（<0.3.0）时 `/api/embed` 不可用，Embedding 降级为 BM25 稀疏检索 + RRF 融合，功能不受影响。

## MCP 工具（可选）

公司创建/搜索等工具逻辑在 `backend/mcp_company/service.py`，直接调用后端服务函数；如需从外部 MCP 客户端调用，参考该模块接口自行包装。

## 后台任务

`core/task_manager.py`：PostgreSQL 持久化 TaskRecord + worker 循环 + 自动重试 + 去重 + 启动恢复。快速研究（`research/quick.py`）即通过它后台跑 计划→搜集→报告 链，SSE 推流进度。

## 测试

```bash
make test        # pytest，专用 airesearch_test 库 + 隔离 Qdrant 集合
```
当前 **125 passed**。
