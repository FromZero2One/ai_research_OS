# AI Research OS — 系统架构与数据流文档

> 最后更新: 2026-07-29  
> 项目定位: 个人 AI 驱动的投资研究助理  
> 架构原则: **Research First, not AI First** — AI 是研究流程中的能力，不是中心

---

## 目录

1. [整体架构概览](#1-整体架构概览)
2. [技术栈](#2-技术栈)
3. [目录结构](#3-目录结构)
4. [7 大业务模块](#4-7-大业务模块)
5. [数据流详解](#5-数据流详解)
6. [行情数据链路](#6-行情数据链路)
7. [AI 能力](#7-ai-能力)
8. [数据库与存储](#8-数据库与存储)
9. [前端路由与组件](#9-前端路由与组件)

---

## 1. 整体架构概览

```
┌─────────────────────────────────────────────────────────┐
│                  前端 (Vue 3 + Vite)                     │
│  TypeScript · Element Plus · ECharts · TanStack VueQuery│
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 工作台    │ │ 研究     │ │ 行情     │ │ 公司     │  │
│  │ Dashboard│ │ Research │ │ Market   │ │ Companies│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 文档     │ │ 知识库   │ │ AI 中心  │ │ 投资组合 │  │
│  │ Documents│ │ Knowledge│ │ AI       │ │ Portfolio│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────────────────────────────────┐              │
│  │ 系统 System (调度器/观测/API健康)     │              │
│  └──────────────────────────────────────┘              │
│                   │ Vite Dev Proxy                       │
│           /api/* → localhost:8000/api/v1/*              │
└──────────────────────┬──────────────────────────────────┘
                       │ HTTP
┌──────────────────────▼──────────────────────────────────┐
│              后端 (FastAPI + Python)                     │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ Company  │ │ Market   │ │ Research │ │ AI       │  │
│  │ 公司管理  │ │ 行情中心 │ │ 研究引擎 │ │ AI 集成  │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘  │
│  ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐ ┌────▼─────┐  │
│  │Document  │ │Knowledge │ │Portfolio │ │Dashboard │  │
│  │ 文档管理 │ │ 知识库   │ │ 投资组合 │ │ 工作台   │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                         │
│  ┌──────────────────────────────────────────────────┐   │
│  │              Core 基础设施                        │   │
│  │  Config · Database · EventLog · Embedding · LLM  │   │
│  │  Scheduler · ObservationEngine · CRUD · Security │   │
│  │  Adapters: AkshareMySQL · Ollama · Qdrant · Redis│   │
│  └──────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│              外部数据源 / 基础设施                        │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │PostgreSQL│ │ Qdrant   │ │ Redis    │ │ MySQL    │  │
│  │ pgvector │ │ 向量数据库│ │ 缓存     │ │ akshare  │  │
│  │ 主数据库  │ │          │ │          │ │ 行情库   │  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                                                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│  │ Ollama   │ │ akshare  │ │ 云 MCP   │                │
│  │ BGE-M3   │ │ 本地进程 │ │ 8.137... │                │
│  │ 嵌入模型  │ │ 数据源   │ │ 备用     │                │
│  └──────────┘ └──────────┘ └──────────┘                │
└─────────────────────────────────────────────────────────┘
```

**mcp_company 模块**: `backend/mcp_company/service.py` 是 MCP 公司工具的**内部实现**，直接调用后端服务函数（`CompanyService`、`SearchService`、`ProfileService`），共享同一 DB session 生命周期。不再有单独的 MCP 服务器入口 — 功能已完全被前端 UI 覆盖。

---

## 2. 技术栈

### 后端

| 技术 | 用途 | 版本 |
|------|------|------|
| Python | 运行时 | 3.13 |
| FastAPI | Web 框架 | 0.115+ |
| SQLAlchemy 2.0 | ORM (async) | 2.0+ |
| Alembic | 数据库迁移 | latest |
| PostgreSQL + pgvector | 主数据库 + 向量搜索 | 16 |
| Qdrant | 向量数据库 | latest |
| Redis | 缓存 | 7-alpine |
| akshare | A股/港股数据源 | latest |
| pymysql | MySQL 适配器 | 1.0+ |
| Ollama | 本地嵌入 (BGE-M3) | latest |
| APScheduler | 定时任务 | 3.10+ |

### 前端

| 技术 | 用途 |
|------|------|
| Vue 3 | 框架 (Composition API) |
| Vite | 构建工具 (dev 默认端口 5173) |
| TypeScript | 类型安全 |
| Element Plus | UI 组件库 |
| ECharts | 图表 (K线/财务趋势图) |
| TanStack Vue Query | 数据请求 + 缓存 |
| Pinia | 状态管理 |
| Vue Router | 路由 |

### 基础设施

| 服务 | 端口 | 用途 |
|------|------|------|
| PostgreSQL | 5432 | 主数据库 |
| Qdrant | 6333/6334 | 向量存储 |
| Redis | 6380 | 缓存 |
| MySQL (外部) | 3306 | akshare 行情库 |
| Ollama | 11434 | 嵌入模型服务 |
| 前端 (Vite) | 5173 | 开发服务器 |
| 后端 (FastAPI) | 8000 | API 服务 |

---

## 3. 目录结构

```
ai_research_OS/
├── backend/                    # Python FastAPI 后端
│   ├── api/
│   │   └── app.py              # FastAPI app factory (11 routers)
│   ├── ai/                     # AI 中心 (prompt模板/生成/摘要/工作流)
│   ├── alembic/                # 数据库迁移
│   ├── company/                # 公司中心 (CRUD+标签+Thesis)
│   ├── core/                   # 核心基础设施
│   │   ├── adapters/           # 外部适配器
│   │   │   ├── akshare_mysql.py    # akshare MySQL 适配器(读)
│   │   │   ├── embedding.py        # Ollama BGE-M3 嵌入
│   │   │   ├── llm.py             # LLM 适配器 (DeepSeek/Ollama)
│   │   │   ├── vector_store.py     # Qdrant 向量存储
│   │   │   └── cache.py           # Redis 缓存
│   │   ├── config.py           # pydantic-settings 配置
│   │   ├── database.py         # 异步 SQLAlchemy 引擎
│   │   ├── crud.py             # 通用 CRUD
│   │   ├── security.py         # JWT + bcrypt
│   │   ├── exceptions.py       # 异常体系 (6种)
│   │   ├── event_log.py        # 审计日志模型
│   │   ├── event_service.py    # 事件读写服务 (read + query + write)
│   │   ├── event_routes.py     # 事件日志查询 API (4 个端点)
│   │   ├── logging.py          # structlog 配置
│   │   ├── scheduler.py        # APScheduler
│   │   ├── scheduler_jobs.py   # 定时任务 (3个)
│   │   ├── scheduler_routes.py # 调度器 API (含后台任务查询/重试)
│   │   ├── task_manager.py     # 持久化后台任务 (TaskRecord + Worker循环 + 启动恢复)
│   │   └── observation_engine.py # 自选股观测
│   ├── dashboard/              # 工作台 (聚合数据,只读)
│   ├── document/               # 文档中心 (上传/解析/索引)
│   ├── knowledge/              # 知识库 (RAG: Dense+Sparse+RRF)
│   ├── market/                 # 行情中心 (K线/财务/搜索)
│   ├── portfolio/              # 投资组合 (自选/持仓/日记)
│   ├── research/               # 研究中心 (会话/证据/报告)
│   │   ├── quick.py            # 快速研究 (SSE 流式)
│   │   ├── timeline.py         # 研究时间线 (路由层)
│   │   ├── timeline_service.py # 时间线聚合查询 (TimelineService)
│   │   └── session_service.py  # 研究会话CRUD + 进度追踪
│   ├── scripts/                # 工具脚本
│   │   ├── seed_data.py        # 种子数据
│   │   └── seed_market_data.py # 行情种子
│   └── tests/                  # 测试
├── frontend/                   # Vue 3 + Vite 前端
│   └── src/
│       ├── main.ts             # 应用入口
│       ├── App.vue             # 根组件
│       ├── router/index.ts     # 13 个路由
│       ├── stores/api.ts       # TanStack VueQuery hooks
│       ├── types/              # 自动生成的 API 类型
│       │   ├── api.ts          # openapi-typescript (npm run gen)
│       │   └── helpers.ts      # ApiResponse<T> 便捷类型
│       ├── components/         # 共享组件
│       │   ├── CommandPalette.vue  # ⌘K 命令面板
│       │   ├── Sidebar.vue         # 侧边栏导航
│       │   ├── StockChart.vue      # ECharts K 线图
│       │   └── StockSearch.vue     # 可复用股票搜索 (v-model + 防抖 + 键盘导航)
│       ├── views/              # 页面视图
│       │   ├── Dashboard.vue   # 工作台首页
│       │   ├── Companies.vue   # 公司列表
│       │   ├── CompanyDetail.vue # 公司详情
│       │   ├── Market.vue      # 行情中心
│       │   ├── ResearchList.vue  # 研究会话列表
│       │   ├── ResearchQuick.vue # 快速研究
│       │   ├── ResearchDetail.vue # 研究详情
│       │   ├── ResearchTimeline.vue # 时间线
│       │   ├── Documents.vue   # 文档管理
│       │   ├── Knowledge.vue   # 知识库
│       │   ├── AICenter.vue    # AI 中心
│       │   ├── Portfolio.vue   # 投资组合
│       │   └── System.vue      # 系统状态
│       └── styles/             # 全局样式
├── docker/
│   ├── docker-compose.yml      # PostgreSQL + Qdrant + Redis
│   └── init.sql                # 初始化 SQL
├── backend/mcp_company/        # MCP 工具内部实现 (直接调用后端服务)
├── docs/                       # 文档
├── scripts/                    # 项目脚本
├── README.md                   # 快速开始
└── USAGE.md                    # 完整使用手册
```

---

## 4. 7 大业务模块

模块依赖方向: **自下而上，上层可依赖下层**

```
   Company
     ↓
   Market + Document
     ↓
   Knowledge (RAG)
     ↓
   AI
     ↓
   Research
     ↓
   Portfolio
```

每个模块遵循: `models.py` → `schemas.py` → `service.py` → `routes.py`

---

### 4.1 Company — 公司管理

**数据模型** (`backend/company/models.py`)

```
Company
├── id: UUID (PK)
├── ticker: String(16) UNIQUE INDEX  ← 股票代码
├── name: String(256)              ← 公司全称
├── description: Text?             ← 公司简介
├── sector: String(128)?           ← 行业板块
├── industry: String(128)?         ← 细分行业
├── headquarters: String(256)?     ← 总部地址
├── founded_year: Int?             ← 成立年份
├── employees: Int?                ← 员工数
├── website: String(512)?          ← 官网
├── is_active: Bool                ← 是否启用
├── tags: [CompanyTag]             ← 标签（一对多）
│   ├── id: UUID
│   └── tag: String(64)
├── created_at
└── updated_at
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/companies | 列表(支持搜索/分页) |
| POST | /api/v1/companies | 创建公司 |
| GET | /api/v1/companies/{id} | 详情 |
| PATCH | /api/v1/companies/{id} | 更新 |
| DELETE | /api/v1/companies/{id} | 删除 |
| GET | /api/v1/companies/by-ticker/{ticker}/workspace | 工作区(含观点+研究) |
| POST | /api/v1/companies/by-ticker/{ticker}/thesis | 更新投资观点 |

**数据流**

```
创建公司
  用户输入搜索 → useStockSearch
    → GET /market/search?query=xxx
    → 选择股票 → 自动填充 ticker + name
    → POST /companies { ticker, name, tags }
    → 创建后自动触发:
        POST /market/profile/{ticker}/ingest  (拉取概览)
        POST /market/financials/{ticker}/ingest (拉取财务)

mcp-company 创建公司 (AI 工具入口)
  工具 call create_company("600519")
    → server.py → backend.mcp_company.service.create_company()
    → ProfileService.get_stock_profile()  (直接调用, 无HTTP)
    → CompanyService.create()              (直接调用, 无HTTP)
    → 后台 task: 刷新财务+profile
  (注: 不再 HTTP 自调用后端 API — 直接调用内部服务层)
  新增 StockSearch 组件: 5 个视图共享同一搜索组件
```

---

### 4.2 Market — 行情中心

**数据模型** (`backend/market/models.py`)

```
StockPrice
├── id: UUID (PK)
├── ticker: String(16) INDEX       ← 股票代码
├── date: Date INDEX               ← 交易日
├── open: Float?                   ← 开盘价
├── high: Float?                   ← 最高价
├── low: Float?                    ← 最低价
├── close: Float?                  ← 收盘价
├── volume: Float?                 ← 成交额(元)
├── adjusted_close: Float?         ← 复权收盘价
├── created_at
└── updated_at

FinancialMetric
├── id: UUID (PK)
├── ticker: String(16) INDEX
├── fiscal_year: Int               ← 财年
├── fiscal_period: String(16)      ← 期间 (Q1/Q2/Q3/Annual)
├── metric_name: String(64)        ← 指标名 (revenue, net_income, eps...)
├── metric_value: Float            ← 指标值
├── created_at
└── updated_at
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/market/prices/{ticker} | K 线数据 |
| POST | /api/v1/market/prices/{ticker}/ingest | 采集行情到 PG |
| GET | /api/v1/market/financials/{ticker} | 财务指标 |
| POST | /api/v1/market/financials/{ticker}/ingest | 采集财务(港股) |
| POST | /api/v1/market/profile/{ticker}/ingest | 采集公司概览 |
| GET | /api/v1/market/stock-profile/{ticker} | 股票基础信息(名称/行业/K线) |
| GET | /api/v1/market/search?query=xxx | 搜索股票 |
| GET | /api/v1/market/info/{ticker} | A 股基本信息+估值 |
| GET | /api/v1/market/symbols | 有 K 线数据的股票列表 |
| GET | /api/v1/market/news/{ticker} | 股票新闻 |

**数据流** (详见第 6 节行情数据链路)

---

### 4.3 Document — 文档中心

**数据模型** (`backend/document/models.py`)

```
Document
├── id: UUID (PK)
├── company_id: UUID (FK → company.companies)
├── title: String(256)
├── doc_type: String(32)          ← report/transcript/article/other
├── file_path: String(512)
├── file_size: Int?
├── is_indexed: Bool              ← 是否已嵌入向量库
├── chunk_count: Int?             ← 切片数
├── created_at
└── tags: [DocumentTag]
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/documents | 文档列表 |
| POST | /api/v1/documents/upload | 上传文档(自动解析+索引) |
| DELETE | /api/v1/documents/{id} | 删除 |

**数据流**

```
上传文档
  → POST /documents/upload (multipart)
  → 保存文件到 backend/data/uploads/
  → 创建 Document 记录
  → 自动解析: PDF→文本→切片(chunk)→Ollama BGE-M3→存入Qdrant
```

---

### 4.4 Knowledge — 知识库 (RAG)

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/knowledge/search?query=xxx&top_k=10 | 混合 RAG 搜索 |

**搜索策略: 3 路融合**

```
query → create_embedding(query) → Ollama BGE-M3 (768维)
  ├→ Dense: Qdrant 向量相似度搜索
  ├→ Sparse: BM25 关键词搜索 (jieba分词)
  └→ RRF 融合排序 → 返回最终结果
```

---

### 4.5 AI — AI 能力中心

**数据模型** (`backend/ai/models.py`)

```
PromptTemplate
├── name: String(64) UNIQUE          ← 模板名称
├── system_prompt: Text              ← 系统提示词
├── user_prompt_template: Text       ← 用户提示词模板 (含 {{var}})
├── temperature: Float?              ← 覆盖温度
├── max_tokens: Int?
├── output_schema: JSONB?            ← 结构化输出 schema
└── is_active: Bool

AIWorkflow
├── name: String(128) UNIQUE
├── steps: JSONB                     ← [{"type": "llm", "prompt": ...}, ...]
└── is_active: Bool
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/v1/ai/templates | 模板列表/创建 |
| GET/PATCH/DELETE | /api/v1/ai/templates/{id} | 模板 CRUD |
| POST | /api/v1/ai/generate | 执行模板 (变量替换→LLM) |
| POST | /api/v1/ai/summarize | 文本摘要 |
| POST | /api/v1/ai/extract | 结构化提取 |
| POST | /api/v1/ai/workflows | 创建工作流 |
| POST | /api/v1/ai/workflows/{id}/execute | 执行工作流 |

**LLM 配置** (默认: DeepSeek V4 Flash)

```env
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-deepseek-api-key
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
```

---

### 4.6 Research — 研究中心 (核心)

**数据模型** (`backend/research/models.py`)

```
ResearchSession
├── id: UUID (PK)
├── company_id: UUID (FK)
├── title: String(256)
├── question: Text?                ← 研究问题
├── status: String(32)             ← draft/researching/completed
├── thesis: Text?                  ← 投资观点
├── decision: String(16)?          ← buy/sell/hold/watch/pass
├── confidence: Float?             ← 0-1
├── plan: JSONB?                   ← 研究计划
├── created_at
└── updated_at

ResearchEvidence
├── id: UUID (PK)
├── session_id: UUID (FK)
├── content: Text
├── source_type: String(32)        ← document/market_data/web/ai_generated
├── evidence_type: String(16)      ← supporting/opposing/neutral
├── relevance_score: Float?
└── source_title: String(256)?

ResearchReport
├── id: UUID (PK)
├── session_id: UUID (FK)
├── content: Text
├── version: Int                   ← 自动递增
└── is_final: Bool
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/v1/research/sessions | 列表/创建 |
| GET/PATCH/DELETE | /api/v1/research/sessions/{id} | 会话 CRUD |
| POST | /api/v1/research/sessions/{id}/plan | 生成研究计划 |
| POST | /api/v1/research/sessions/{id}/auto-gather | 自动搜集证据 |
| GET/POST | /api/v1/research/sessions/{id}/evidences | 证据管理 |
| GET/POST | /api/v1/research/sessions/{id}/reports | 报告管理 |
| POST | /api/v1/research/sessions/{id}/finalize | 最终化 |
| POST | /api/v1/research/quick | 一键快速研究 |
| GET | /api/v1/research/quick/{id}/stream | SSE 进度流 |
| GET | /api/v1/research/timeline | 时间线 |
| GET | /api/v1/research/sessions/{id}/timeline | 会话时间线 |
| GET | /api/v1/research/reports/{id}/diff | 报告 diff |

**标准研究流程**

```
1. 选择公司 → 提出研究问题
2. 创建研究会话 (POST /research/sessions)
3. 生成研究计划 (AI: 6个子问题/6个分析维度)
4. 收集证据: 自动搜索知识库 + 手动添加
5. 生成研究报告 (AI 综合计划+证据)
6. 最终化: thesis + decision(buy/sell/hold/watch/pass) + confidence
```

---

### 4.7 Portfolio — 投资组合

**数据模型** (`backend/portfolio/models.py`)

```
Watchlist
├── id: UUID (PK)
├── name: String(256)
├── description: Text?
├── items: [WatchlistItem]
│   ├── ticker: String(16)
│   ├── company_id: UUID (FK)
│   ├── priority: Int (1-5, default 3)
│   ├── notes: Text?
│   ├── target_price: Float?
│   └── status: String ← normal/attention/need_research
└── created_at

Holding
├── id: UUID (PK)
├── company_id: UUID (FK)
├── quantity: Float?
├── avg_cost: Float?
├── is_active: Bool
└── created_at

InvestmentJournal
├── id: UUID (PK)
├── title: String(256)
├── content: Text
├── company_id: UUID? (FK)
├── session_id: UUID? (FK)
└── created_at
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /api/v1/portfolio/watchlists | 自选列表 |
| GET/DELETE | /api/v1/portfolio/watchlists/{id} | 列表详情 |
| POST | /api/v1/portfolio/watchlists/{id}/items | 添加自选 |
| DELETE | /api/v1/portfolio/watchlists/items/{id} | 移除自选 |
| GET/POST | /api/v1/portfolio/holdings | 持仓 |
| PATCH | /api/v1/portfolio/holdings/{id} | 更新持仓 |
| POST | /api/v1/portfolio/holdings/{id}/close | 平仓 |
| GET/POST | /api/v1/portfolio/journal | 投资日记 |

### 4.8 Dashboard — 工作台

**无数据模型** — 只读聚合

```
GET /api/v1/dashboard
  ├→ morning_brief (最新AI生成简报)
  ├→ watchlist (自选股+最新股价+研究状态)
  ├→ research_reminders (>30天未研究标红)
  └→ recent_research (最近5条研究会话)
```

### 4.9 Scheduler — 调度器

基于 APScheduler (AsyncIOScheduler)，时区 Asia/Shanghai

```
3 个定时任务:
├── market_data_update (工作日 2:00) — 遍历公司拉取最新行情
├── morning_brief (工作日 6:00)      — AI 生成晨间简报
└── observation_cycle (工作日 5:30)  — 自选股观测(14天/30天提醒)
```

---

## 5. 数据流详解

### 5.1 数据流总图

```
外部数据源                        内部存储                    前端展示
┌────────────┐   采集    ┌──────────────┐   查询    ┌──────────────┐
│ akshare    │ ───────→ │ PostgreSQL   │ ←────── │ 行情中心     │
│ 腾讯源     │  3层降级  │ StockPrice   │         │ K线图/财务   │
│ 新浪源     │          │ FinancialMetric│        │              │
│ 东财港股   │          │              │         │              │
└────────────┘          └──────────────┘         └──────────────┘
┌────────────┐   查询    ┌──────────────┐   查询    ┌──────────────┐
│ akshare    │ ───────→ │ PostgreSQL   │ ←────── │ 公司列表     │
| MySQL      |          │ Company      |         │ 公司详情     │
│ (本地3306) │          │ CompanyTag   │         │ 编辑/搜索    │
└────────────┘          └──────────────┘         └──────────────┘
┌────────────┐   嵌入    ┌──────────────┐   搜索    ┌──────────────┐
│ Ollama     │ ───────→ │ Qdrant       │ ←────── │ 知识库       │
│ BGE-M3     │ 向量化   │ 文档嵌入     │         │ 语义搜索     │
└────────────┘          └──────────────┘         └──────────────┘
┌────────────┐   调用    ┌──────────────┐   对话    ┌──────────────┐
│ DeepSeek   │ ←──────→ │ AI 服务      │ ←────── │ AI 中心      │
│ LLM API    │ 流式     │ Chat/Search  │         │ 研究助手     │
└────────────┘          └──────────────┘         └──────────────┘
```

### 5.2 公司数据流

```
┌─────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 创建公司  │ → │ 填充信息  │ → │ 查看详情  │ → │ 关联研究  │
└────┬─────┘   └────┬─────┘   └────┬─────┘   └────┬─────┘
     │               │              │               │
     ▼               ▼              ▼               ▼
  POST /companies  POST /market/  GET /companies/  GET /research/
                   profile/ingest  {id}/workspace  sessions?company=
     │               │              │               │
     │  useStockSearch()            │               │
     │  → GET /market/search       │               │
     │  → 自动填充 ticker+name     │               │
     │               │              │               │
     ▼               ▼              ▼               ▼
  Company +        stock_profile_  Company +       ResearchSession
  CompanyTag       cninfo (A股)    Thesis +        + EventLog
                   cninfo (港股)    Timeline
```

---

## 6. 行情数据链路

### 6.1 三层降级采集链

整个系统只有**后端 MarketService** 维护采集链路，mcp-company 不再直连 MySQL。

```
                    ┌─ Layer 1: MySQL (10ms) ─────────────────┐
                    │  AkshareMySQLAdapter                    │
                    │  host: 127.0.0.1:3306                  │
                    │  database: akshare                      │
                    │  表: stock_zh_a_hist (日K线)            │
                    │      stock_yjbb_em (财务指标)           │
                    │      stock_name_entity (名称映射)        │
                    └────────────────────────────────────────┘
                               ↓ 无数据
                    ┌─ Layer 2: 本地 akshare (3-10s) ─────────┐
                    │  subprocess → uv run → akshare          │
                    │  A 股: stock_zh_a_hist_tx (腾讯源)       │
                    │  港股: stock_hk_daily (新浪源)           │
                    └────────────────────────────────────────┘
                               ↓ 无数据
                    ┌─ Layer 3: 云 MCP (1-3s) ────────────────┐
                    │  8.137.104.120:8088/mcp                 │
                    │  MCP ClientSession → 备用               │
                    └────────────────────────────────────────┘
```

### 6.2 核心数据路径

```
价格查询: GET /market/prices/{ticker}
  → 1. 查 PostgreSQL (已采集数据)
  → 2. A股 → MySQL (Layer 1)
  → 3. 自动采集 3 层降级 → 写入 PG → 返回

股票搜索: GET /market/search?query=xxx
  → 1. PostgreSQL Company 表 (A股/港股/美股)
  → 2. MySQL stock_name_entity (A股)
  → 合并去重返回

股票信息: GET /market/stock-profile/{ticker}
  → MySQL: stock_name_entity → name
  → MySQL: stock_yjbb_em → sector
  → MySQL: stock_zh_a_hist → has_kline
  → 用于 mcp-company 创建公司
```

---

## 7. AI 能力

### 7.1 嵌入模型

```
create_embedding(text) → float[768]
  └→ EMBEDDING_PROVIDER = "ollama"
      → Ollama API: /api/embed (BGE-M3)
      → HTTP POST to http://127.0.0.1:11434
      → 768 维向量
      → 备用: sentence-transformers (需 pip install embedding)
```

### 7.2 LLM 配置

默认使用 DeepSeek V4 Flash (云端 API)：

```env
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
OPENAI_API_KEY=sk-your-key
```

备用选项:
- Ollama 本地 (qwen3.5)
- 通义千问 / Moonshot (OpenAI 兼容)

---

## 8. 数据库与存储

### 8.1 PostgreSQL (主数据库)

Schema: `public` + `company` + `market` + `document` + `research` + `portfolio` + `ai` + `knowledge` + `event_log`

| 表 | Schema | 用途 |
|----|--------|------|
| companies | company | 公司信息 |
| company_tags | company | 公司标签 |
| stock_prices | market | 日K线数据 |
| financial_metrics | market | 财务指标 |
| documents | document | 文档元数据 |
| document_chunks | document | 文档切片 |
| knowledge_entries | knowledge | 知识库条目 |
| prompt_templates | ai | AI 提示词模板 |
| ai_workflows | ai | AI 工作流 |
| research_sessions | research | 研究会话 |
| research_evidences | research | 研究证据 |
| research_reports | research | 研究报告 |
| watchlists | portfolio | 自选列表 |
| watchlist_items | portfolio | 自选项目 |
| holdings | portfolio | 持仓记录 |
| journal_entries | portfolio | 投资日记 |
| event_log | core | 审计日志 (只追加) |
| task_records | core | 持久化后台任务队列 |
| morning_briefs | core | AI 晨间简报 |
| observations | core | 自选股观察记录 |
| data_freshness | market | 数据新鲜度追踪 (每个ticker+data_type) |

### 8.2 MySQL (外部 akshare 行情库)

| 表 | 用途 |
|----|------|
| stock_zh_a_hist | A 股日 K 线 (腾讯数据源) |
| stock_yjbb_em | A 股财务指标 |
| stock_value_em | A 股估值 (PE/PB) |
| stock_name_entity | A 股代码-名称映射 |

> 此 MySQL 由外部 akshare MCP 服务维护，不在本项目 docker-compose 中。

### 8.3 Qdrant (向量数据库)

存储文档嵌入向量 (768维 BGE-M3)，用于知识库语义搜索。

### 8.4 Redis (缓存)

缓存热点数据，默认 TTL 3600s。

---

## 9. 前端路由与组件

### 9.1 页面路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | Dashboard | 工作台 (Morning Brief + 自选股 + 研究提醒) |
| `/companies` | Companies | 公司列表 + 创建/搜索 |
| `/companies/:id` | CompanyDetail | 公司详情 (概览/观点/财务/研究/文档) |
| `/market` | Market | 行情中心 (搜索+K线+财务) |
| `/research` | ResearchList | 研究会话列表 |
| `/research/quick` | ResearchQuick | 快速研究 (输入→AI分析→报告) |
| `/research/:id` | ResearchDetail | 研究会话详情 |
| `/research/timeline` | ResearchTimeline | 研究时间线 (按公司/按会话) |
| `/documents` | Documents | 文档管理 (上传/查看/删除) |
| `/knowledge` | Knowledge | 知识库搜索 |
| `/ai` | AICenter | AI 中心 (对话/模板/工作流) |
| `/portfolio` | Portfolio | 投资组合 (自选/持仓/日记) |
| `/system` | System | 系统状态 (调度器/观测/API健康) |

### 9.2 共享组件

| 组件 | 用途 |
|------|------|
| Sidebar.vue | 侧边栏导航 (当前路由高亮) |
| StockChart.vue | ECharts K 线图 (MA5/MA20/成交量/dataZoom) |
| CommandPalette.vue | ⌘K 全局命令面板 (11 条命令) |

### 9.3 API 连接

前端通过 Vite proxy (`vite.config.ts`) 将 `/api` 代理到 `http://localhost:8000/api/v1`。

```
/api/companies        → /api/v1/companies
/api/market/prices/X  → /api/v1/market/prices/X
/api/research/...     → /api/v1/research/...
```

TanStack VueQuery hooks (`stores/api.ts`) 提供类型安全的 API 调用:

| Hook | 端点 |
|------|------|
| useCompanies | GET /companies |
| useCompany(id) | GET /companies/{id} |
| useCreateCompany | POST /companies |
| useMarketPrices(ticker) | GET /market/prices/{ticker} |
| useStockSearch(query) | GET /market/search |
| useFinancialMetrics(ticker) | GET /market/financials/{ticker} |
| useResearchSessions | GET /research/sessions |
| useQuickResearch | POST /research/quick |
| useDashboard | GET /dashboard |
| useCompanyThesis(ticker) | GET /companies/by-ticker/{ticker}/thesis |
| useUpdateThesis | POST /companies/by-ticker/{ticker}/thesis |
| useCompanyWorkspace(ticker) | GET /companies/by-ticker/{ticker}/workspace |
| useWatchlists | GET /portfolio/watchlists |
| useHoldings | GET /portfolio/holdings |
| useDocuments | GET /documents |
| useUploadDocument | POST /documents/upload |

---

## 附录: 关键配置

```env
# backend/.env
LLM_PROVIDER=openai
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash

QDRANT_HOST=localhost
QDRANT_PORT=6333

EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_EMBEDDING_MODEL=bge-m3

REDIS_URL=redis://localhost:6380/0
SCHEDULER_ENABLED=false
```

```typescript
// frontend/vite.config.ts
server: {
  proxy: {
    '/api': { target: 'http://localhost:8000', rewrite: p => p.replace(/^\/api/, '/api/v1') },
    '/health': { target: 'http://localhost:8000' },
  },
}
```

---

> 本文档基于对项目代码的全面分析。文档由 Claude Code 维护，项目迭代时需同步更新。
