# AI Research OS — 开发进度记录

**最后更新**: 2026-07-18

---

## 完成状态总览

| 模块 | 状态 | 备注 |
|------|------|------|
| Core Layer | ✅ 完成 | config, database, interfaces, event_log, security, logging, cache |
| Adapters | ✅ 完成 | LLM (Ollama/OpenAI), Embedding, Qdrant, Redis |
| Company Center | ✅ 完成 | model, schema, service, routes |
| Market Center | ✅ 完成 | model, schema, service, routes |
| Document Center | ✅ 完成 | model, schema, service, routes, chunker |
| Knowledge Center | ✅ 完成 | Hybrid RAG (dense + sparse) |
| AI Center | ✅ 完成 | prompt management, workflows, generate/summarize/extract |
| Research Center | ✅ 完成 | full CRUD + evidence + reports + finalize |
| Portfolio Center | ✅ 完成 | watchlist, holdings, journal |
| API Gateway | ✅ 完成 | FastAPI app factory, middleware, exception handlers, CORS |
| Frontend | ✅ 代码完成 | 7 pages + sidebar + API client (npm install 已跑完) |
| Database | ✅ 已运行 | PostgreSQL (pgvector) + Qdrant + Redis (6380端口) |
| 种子数据 | ✅ 已导入 | 8 家样本公司 + 1 个 NVDA 研究会话 |
| API 测试 | ⚠️ 部分通过 | CRUD 接口全部通过，Document 有 proxy 问题 |

---

## 目录结构

```
ai-research-os/
├── backend/
│   ├── core/                  # 核心层
│   │   ├── config.py             配置管理 (pydantic-settings)
│   │   ├── database.py           异步 SQLAlchemy 引擎
│   │   ├── base.py               Declarative Base + Timestamp/UUID mixin
│   │   ├── interfaces.py         协议定义 (LLM, Vector, Embedding, Cache...)
│   │   ├── exceptions.py         自定义异常
│   │   ├── logging.py            structlog 日志配置
│   │   ├── security.py           JWT + bcrypt
│   │   ├── event_log.py          事件审计表模型
│   │   ├── event_service.py      事件记录服务
│   │   ├── crud.py               通用 CRUD base
│   │   └── adapters/
│   │       ├── llm.py            Ollama / OpenAI 实现
│   │       ├── embedding.py      SentenceTransformer (BGE-M3)
│   │       ├── vector_store.py   Qdrant 实现
│   │       └── cache.py          Redis 实现
│   ├── company/               # 公司中心
│   ├── market/                # 市场中心
│   ├── document/              # 文档中心
│   │   ├── chunker.py         文本分块器
│   │   └── service.py         完整 pipeline: parse → chunk → embed → index
│   ├── knowledge/             # 知识中心
│   │   └── service.py         Hybrid RAG: Qdrant + BM25 + RRF fusion
│   ├── ai/                    # AI 能力中心
│   ├── research/              # 研究中心 (核心)
│   ├── portfolio/             # 投资中心
│   ├── api/
│   │   └── app.py             FastAPI 应用工厂
│   ├── scripts/
│   │   ├── seed_data.py       样本数据种子
│   │   └── test_finalize.py   测试脚本
│   ├── alembic/               # 数据库迁移
│   ├── .env                   开发环境配置
│   ├── pyproject.toml
│   └── main.py
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx           Dashboard 首页
│   │   │   ├── companies/        公司列表 + 详情
│   │   │   ├── research/         研究会话列表 + 详情
│   │   │   ├── documents/        文档管理
│   │   │   ├── knowledge/        Hybrid Search
│   │   │   ├── market/           市场数据
│   │   │   ├── ai/               AI 能力
│   │   │   └── portfolio/        投资组合
│   │   ├── components/Sidebar.tsx
│   │   └── lib/api.ts            React Query hooks
│   ├── package.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   └── postcss.config.mjs
├── docker/
│   ├── docker-compose.yml      基础设施 (pg, qdrant, redis)
│   ├── docker-compose.full.yml 全栈编排
│   ├── docker-entrypoint-initdb.d/init.sql
│   └── Dockerfile.backend
├── data/                       # 数据目录 (git ignored)
├── scripts/
│   └── install.sh
├── Makefile
└── README.md
```

---

## 已验证通过的 API

### Health
```bash
GET /health
→ {"status":"ok","app":"AI Research OS","version":"0.1.0","env":"development"}
```

### Company Center
```bash
GET  /api/v1/companies               # 列出公司（8 家）
GET  /api/v1/companies?query=AAPL    # 搜索
POST /api/v1/companies               # 创建公司
GET  /api/v1/companies/{id}          # 公司详情（含 tags）
PATCH /api/v1/companies/{id}         # 更新
DELETE /api/v1/companies/{id}        # 删除
```

### Research Center
```bash
GET    /api/v1/research/sessions               # 列表（含 status 过滤）
POST   /api/v1/research/sessions               # 创建研究会话
GET    /api/v1/research/sessions/{id}          # 详情（含 evidences, reports）
PATCH  /api/v1/research/sessions/{id}          # 更新
DELETE /api/v1/research/sessions/{id}          # 删除
POST   /api/v1/research/sessions/{id}/evidences               # 添加证据
GET    /api/v1/research/sessions/{id}/evidences               # 证据列表
DELETE /api/v1/research/evidences/{id}                        # 删除证据
POST   /api/v1/research/sessions/{id}/finalize?thesis=...&decision=...&confidence=...
```

### AI Center
```bash
POST /api/v1/ai/templates              # 创建 prompt 模板
GET  /api/v1/ai/templates              # 列表
GET  /api/v1/ai/templates/{id}         # 详情
POST /api/v1/ai/summarize              # 摘要
POST /api/v1/ai/extract                # 结构提取
```

### Document / Knowledge / Market / Portfolio
- 基础 CRUD endpoints 已定义，但未做端到端验证
- 原因：Qdrant httpx client 被 socks 代理环境变量阻塞

---

## 已知问题（待解决）

### 1. SOCKS 代理环境变量 (`all_proxy=socks://127.0.0.1:7890`)

**影响**: Qdrant 客户端初始化失败，导致 Document/KG 模块不可用

**错误日志**:
```
ValueError: Unknown scheme for proxy URL URL('socks://127.0.0.1:7890/')
```

**根因**: 环境变量 `all_proxy` 设置了 `socks://` 协议，但 httpx 不支持 socks 协议（需要 `httpx[socks]` 扩展）。Qdrant 的 AsyncQdrantClient 内部使用 httpx，启动时读取了这个环境变量。

**解决方案** (三选一):
- **方案 A**: 启动时屏蔽 proxy：`no_proxy=localhost,127.0.0.0/8,::1 PYTHONPATH=. uvicorn api.app:app`
- **方案 B**: 安装 `pip install httpx[socks]` 让 httpx 支持 socks
- **方案 C**: 在 `core/adapters/vector_store.py` 的 Qdrant 初始化处强制清除 proxy 环境变量

### 2. `updated_at` 字段的懒加载问题

**影响**: `flush()` 后 `updated_at` 在 async 模式下触发懒加载异常

**解决方法**: 在 service 层的 `flush()` 后添加 `await self.session.refresh(obj)`。已经修复了以下方法：
- `ResearchService.finalize_thesis()` ✅
- `ResearchService.update_session()` ✅
- `CompanyService.create()` ✅
- `CompanyService.update()` ✅

**待修复**: DocumentService, PortfolioService, AIService, MarketService

### 3. Python 依赖包缺失

需要安装：
```bash
pip install sentence-transformers  # 嵌入模型 (BGE-M3)，约 2.2GB 模型下载
```

### 4. Frontend npm peer dependencies

已用 `--legacy-peer-deps` 解决（npm install 已完成）。但需要验证构建是否正常。

---

## 如何继续开发

### 启动开发环境 (按顺序)

```bash
# 1. 基础设施
cd ai-research-os && docker compose -f docker/docker-compose.yml up -d

# 2. 设置 proxy (避免 Qdrant httpx 问题)
export no_proxy="localhost,127.0.0.0/8,::1"

# 3. 启动后端
cd backend && PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

# 4. 启动前端 (另一个终端)
cd frontend && npm run dev
```

### 测试命令

```bash
cd backend

# 运行所有数据库 CRUD API 测试
PYTHONPATH=. python3 -m pytest -v tests/ -x --asyncio-mode=auto  # (需要先创建 tests/)

# 运行种子数据
PYTHONPATH=. python3 scripts/seed_data.py

# 测试 finalize 流程
PYTHONPATH=. python3 scripts/test_finalize.py
```

### 数据库迁移 (schema 变更后)

```bash
cd backend
alembic revision --autogenerate -m "description"
alembic upgrade head
```

---

## 下一步开发的建议顺序

1. **修复 SOCKS 代理问题** → Document/Knowledge/Market 模块可用
2. **验证 Document 上传→解析→嵌入→搜索完整 pipeline**
3. **运行前端** → 验证 Dashboard pages
4. **编写单元测试**
5. **安装 sentence-transformers** → embedding 管道可用
6. **添加用户认证**（目前绕过）
