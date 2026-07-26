# AI Research OS — 系统架构与数据流文档

> 最后更新: 2026-07-26  
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
10. [开发与部署](#10-开发与部署)

---

## 1. 整体架构概览

```
┌─────────────────────────────────────────────────────────┐
│                  前端 (Next.js 15)                       │
│  React 19 · Tailwind CSS 4 · ECharts · React Query v5  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 工作台    │ │ 研究     │ │ 行情     │ │ 公司     │  │
│  │ Dashboard│ │ Research │ │ Market   │ │ Companies│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │ 文档     │ │ 知识库   │ │ AI 中心  │ │ 投资组合 │  │
│  │ Documents│ │ Knowledge│ │ AI       │ │ Portfolio│  │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                   │ Next.js Rewrite Proxy               │
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
│  │  Config · Database · Event Bus · Embedding · MCP │   │
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

---

## 2. 技术栈

### 后端

| 技术 | 用途 | 版本 |
|------|------|------|
| Python | 运行时 | 3.10 |
| FastAPI | Web 框架 | latest |
| SQLAlchemy 2.0 | ORM (async) | 2.0+ |
| Alembic | 数据库迁移 | latest |
| PostgreSQL + pgvector | 主数据库 + 向量搜索 | 16 |
| Qdrant | 向量数据库 (备用) | latest |
| Redis | 缓存 | 7-alpine |
| akshare | A股/港股数据源 | latest |
| MCP (Model Context Protocol) | 数据采集通道 | latest |

### 前端

| 技术 | 用途 | 版本 |
|------|------|------|
| Next.js | 框架 | 15.5 |
| React | UI | 19 |
| Tailwind CSS | 样式 | 4 |
| ECharts | 图表 (K线/财务) | 6.1 |
| TanStack React Query | 数据请求 | 5.60 |
| TypeScript | 类型安全 | 5.x |

### 基础设施

| 服务 | 端口 | 用途 |
|------|------|------|
| PostgreSQL | 5432 | 主数据库 |
| Qdrant | 6333/6334 | 向量存储 |
| Redis | 6380 | 缓存 |
| MySQL (外部) | 3306 | akshare 行情库 |
| Ollama | 11434 | 嵌入模型服务 |

---

## 3. 目录结构

```
ai_research_OS/
├── backend/                    # Python FastAPI 后端
│   ├── api/                    # 应用入口
│   │   └── app.py              # FastAPI app factory
│   ├── ai/                     # AI 模块
│   ├── alembic/                # 数据库迁移
│   ├── company/                # 公司模块
│   ├── core/                   # 核心基础设施
│   │   ├── adapters/           # 外部适配器
│   │   │   ├── akshare_mysql.py    # akshare MySQL 适配器
│   │   │   └── embedding.py        # 嵌入模型适配
│   │   ├── config.py           # 配置
│   │   ├── database.py         # 数据库连接
│   │   ├── event_service.py    # 事件日志
│   │   └── exceptions.py       # 异常定义
│   ├── dashboard/              # 工作台模块
│   ├── data/                   # 上传目录
│   ├── document/               # 文档模块
│   ├── knowledge/              # 知识库模块
│   ├── market/                 # 行情模块
│   ├── portfolio/              # 投资组合模块
│   ├── research/               # 研究模块
│   ├── scripts/                # 脚本工具
│   └── tests/                  # 测试
├── frontend/                   # Next.js 前端
│   └── src/
│       ├── app/                # 页面路由
│       ├── components/         # 共享组件
│       └── lib/                # API 钩子 + 工具
├── docker/                     # Docker Compose 配置
├── docs/                       # 文档
├── mcp-company/                # MCP 公司数据采集 (备用)
└── scripts/                    # 项目脚本
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

查看公司
  → GET /companies/{id} → 基本信息
  → GET /companies/by-ticker/{ticker}/workspace → 观点 + 研究时间线

刷新公司概览
  → POST /market/profile/{ticker}/ingest
    → A 股: stock_profile_cninfo (巨潮)
    → 港股: stock_hk_company_profile_em (东财)
    → 更新 sector, industry, description, website, headquarters, founded_year, employees
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
| POST | /api/v1/market/prices/{ticker}/ingest | 采集行情 |
| GET | /api/v1/market/financials/{ticker} | 财务指标 |
| POST | /api/v1/market/financials/{ticker}/ingest | 采集财务(港股) |
| POST | /api/v1/market/profile/{ticker}/ingest | 采集公司概览 |
| GET | /api/v1/market/search?query=xxx | 搜索股票(代码/名称) |
| GET | /api/v1/market/info/{ticker} | A 股基本信息 |
| GET | /api/v1/market/symbols | 有 K 线数据的股票列表 |

**数据流** (详见第 6 节行情数据链路)

---

### 4.3 Document — 文档管理

**数据模型** (`backend/document/models.py`)

```
Document
├── id: UUID (PK)
├── company_id: UUID (FK → company.companies)
├── title: String(256)
├── file_type: String(32)
├── file_path: String(512)
├── file_size: Int?
├── content_type: String(128)?
├── uploaded_at
├── processed: Bool                ← 是否已处理
└── tags: [DocumentTag]
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/documents | 文档列表 |
| POST | /api/v1/documents/upload | 上传文档(多格式) |
| DELETE | /api/v1/documents/{id} | 删除 |
| POST | /api/v1/documents/{id}/parse | 解析文档内容 |

**数据流**

```
上传文档
  → POST /documents/upload (multipart)
  → 保存文件到 backend/data/uploads/
  → 创建 Document 记录
  → (可选) POST /documents/{id}/parse
    → 提取文本内容
    → 生成嵌入向量 → 存入 Qdrant / PostgreSQL pgvector
    → 关联到知识库
```

---

### 4.4 Knowledge — 知识库 (RAG)

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/knowledge/search?q=xxx | 语义搜索知识库 |
| GET | /api/v1/knowledge/search/bm25?q=xxx | BM25 关键词搜索 |

**数据流**

```
语义搜索
  → GET /knowledge/search?q=xxx
  → create_embedding(query) → Ollama BGE-M3
  → Qdrant / pgvector 相似度搜索
  → 返回匹配的文档片段 + 分数

BM25 搜索
  → GET /knowledge/search/bm25?q=xxx
  → PostgreSQL 全文检索
  → 返回匹配的文档片段 + 分数
```

---

### 4.5 AI — AI 能力中心

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/ai/chat | 对话 (流式) |
| POST | /api/v1/ai/research | 研究分析 |

**LLM 配置** (`backend/core/config.py`)

```python
LLM_PROVIDER = "deepseek"              # 主 LLM
LLM_MODEL = "deepseek-chat"
LLM_API_BASE = "https://api.deepseek.com"
EMBEDDING_PROVIDER = "ollama"          # 嵌入模型
EMBEDDING_MODEL = "bge-m3:latest"
OLLAMA_BASE_URL = "http://localhost:11434"
```

**数据流**

```
AI 对话
  → POST /ai/chat { messages, stream }
  → 调 LLM API (流式返回)
  → 可附带知识库上下文 (RAG)

AI 研究分析
  → POST /ai/research { ticker, query }
  → 收集相关财务数据 + 知识库内容
  → LLM 分析 → 返回研究报告
```

---

### 4.6 Research — 研究引擎

**数据模型** (`backend/research/models.py`)

```
ResearchSession
├── id: UUID (PK)
├── company_id: UUID (FK)
├── title: String(256)
├── status: String(32)               ← draft/in_progress/completed
├── plan: JSON?                      ← 研究计划
├── decision: String(16)?            ← 投资决策 (buy/sell/hold/watch/pass)
├── confidence: Float?               ← 置信度
├── started_at
├── completed_at
└── created_at

TimelineEvent (研究时间线)
├── id: UUID (PK)
├── session_id: UUID (FK)
├── event_type: String(64)           ← research_note/analysis/evidence...
├── content: Text
└── created_at
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/research/sessions | 研究会话列表 |
| POST | /api/v1/research/sessions | 创建会话 |
| GET | /api/v1/research/sessions/{id} | 会话详情 |
| POST | /api/v1/research/quick | 快速研究 |
| GET | /api/v1/research/timeline | 研究时间线 |

**数据流**

```
快速研究
  → POST /research/quick { ticker, query }
  → 收集: 行情数据 + 财务指标 + 知识库内容
  → LLM 分析生成报告
  → 创建 ResearchSession + TimelineEvent
  → 更新 Company 投资观点

研究时间线
  → GET /research/timeline?company_id=xxx
  → 返回该公司的所有研究事件(按时间排序)
  → 前端 Timeline 展示
```

---

### 4.7 Portfolio — 投资组合

**数据模型** (`backend/portfolio/models.py`)

```
Portfolio
├── id: UUID (PK)
├── name: String(256)
├── description: Text?
├── created_at
└── updated_at

PortfolioHolding
├── id: UUID (PK)
├── portfolio_id: UUID (FK)
├── company_id: UUID (FK)
├── ticker: String(16)
├── shares: Float?                   ← 持仓股数
├── avg_cost: Float?                 ← 平均成本
├── target_weight: Float?            ← 目标权重
└── added_at
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/portfolio | 组合列表 |
| POST | /api/v1/portfolio | 创建组合 |
| GET | /api/v1/portfolio/{id} | 组合详情(含持仓) |
| POST | /api/v1/portfolio/{id}/holdings | 添加持仓 |

**数据流**

```
查看组合
  → GET /portfolio/{id}
  → 返回组合信息 + 持仓列表
  → 每个持仓关联 Company + 最新股价
  → 计算市值/盈亏/权重
```

---

### 4.8 AI Center — AI 能力中心

**数据模型** (`backend/ai/models.py`, schema `ai`)

```
PromptTemplate
├── name: String(64) UNIQUE          ← 模板名称
├── description: Text?
├── system_prompt: Text              ← 系统提示词
├── user_prompt_template: Text       ← 用户提示词模板 (含变量 {{var}})
├── model: String(64)?               ← 覆盖模型
├── temperature: Float?              ← 覆盖温度
├── max_tokens: Int?
├── output_schema: JSONB?            ← 结构化输出 schema
└── is_active: Bool

AIWorkflow
├── name: String(128) UNIQUE
├── description: Text?
├── workflow_type: String(32)        ← summarization/extraction/research/...
├── config: JSONB
├── steps: JSONB                     ← [{"type": "llm", "prompt": ...}, ...]
└── is_active: Bool
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /api/v1/ai/templates | 创建 Prompt 模板 |
| GET | /api/v1/ai/templates | 模板列表 |
| GET | /api/v1/ai/templates/{id} | 模板详情 |
| PATCH | /api/v1/ai/templates/{id} | 更新模板 |
| DELETE | /api/v1/ai/templates/{id} | 删除模板 |
| POST | /api/v1/ai/generate | 执行模板 (变量替换 → LLM) |
| POST | /api/v1/ai/summarize | 文本摘要 |
| POST | /api/v1/ai/extract | 结构化提取 |
| POST | /api/v1/ai/workflows | 创建工作流 |
| POST | /api/v1/ai/workflows/{id}/execute | 执行工作流 |

---

### 4.9 Research — 研究引擎（详细）

**数据模型** (`backend/research/models.py`, schema `research`)

```
ResearchSession
├── id: UUID (PK)
├── title: String(256)
├── question: Text?                  ← 研究问题
├── context: Text?                   ← 上下文
├── company_id: UUID (FK)
├── status: String(32)               ← draft/researching/reviewing/completed/archived
├── thesis: Text?                    ← 投资观点
├── decision: String(16)?            ← buy/sell/hold/watch/pass
├── confidence: Float?               ← 0-1
├── tags: JSONB
├── extra_metadata: JSONB            ← 含研究计划、进度等
├── created_at
└── updated_at

ResearchEvidence
├── id: UUID (PK)
├── session_id: UUID (FK)
├── content: Text
├── source_type: String(32)          ← document/market_data/web/ai_generated
├── source_id: String(128)?
├── source_title: String(256)?
├── relevance_score: Float?
├── evidence_type: String(16)        ← supporting/opposing/neutral
├── summary: Text?
└── extra_metadata: JSONB

ResearchReport
├── id: UUID (PK)
├── session_id: UUID (FK)
├── title: String(256)
├── content: Text
├── format: String(16)               ← markdown/html/pdf
├── version: Int                     ← 自动递增
├── is_final: Bool
└── extra_metadata: JSONB
```

**完整研究流程**

```
用户提交问题
  │
  ├→ 1. ResearchService.create_session()
  │   → 创建 ResearchSession (status=draft)
  │   → 可选 auto_plan: 同时生成研究计划
  │
  ├→ 2. ResearchPlanner.generate_plan()
  │   → LLM 生成结构化研究计划
  │   → { research_goal, sub_questions[], analysis_dimensions[], data_requirements[] }
  │
  ├→ 3. ResearchService.auto_gather_evidence()
  │   → 按研究计划搜索:
  │     • KnowledgeService.search() — 知识库语义搜索
  │     • MarketService.get_prices() — 行情数据
  │     • MarketService.get_financials() — 财务数据
  │   → 对每条证据分类 (supporting/opposing/neutral)
  │
  ├→ 4. ResearchService.auto_generate_report()
  │   → 收集所有证据 + 计划 → LLM → markdown 报告
  │   → 版本自动递增
  │
  └→ 5. ResearchService.finalize_thesis()
      → 设置 thesis + decision + confidence
      → status = completed
      → EventLog 记录每一步
```

**快速研究（一键）**

```
POST /research/quick { ticker, question }
  │
  ├→ 1. 解析 ticker → company_id
  ├→ 2. 创建 ResearchSession
  ├→ 3. LLM 生成研究计划
  ├→ 4. 自动收集证据 (知识库 + 行情)
  ├→ 5. LLM 生成报告
  │
  └→ 进度通过 SSE 流推送:
      GET /research/quick/{id}/stream
      → EventSource 监听 progress/complete/error 事件
```

**研究时间线**

```
研究时间线聚合所有研究活动:
  ├→ ResearchSession 创建/状态变更
  ├→ ResearchReport 生成/版本更新
  ├→ EventLog 事件 (证据添加、观点更新...)
  └→ ReportDiff 版本对比

API:
  GET /research/timeline?ticker=xxx      → 公司维度时间线
  GET /research/sessions/{id}/timeline   → 会话维度时间线
  GET /research/reports/{id}/diff?other_version=N → 报告 diff
```

---

### 4.10 Dashboard — 工作台

**无数据模型** — 只读聚合，从其他模块读取数据

**Service** (`DashboardService`)
```
get_dashboard()
  ├→ get_latest_brief()       → EventLog 中取最新的 morning_brief
  ├→ get_watchlist_summary()  → 组合 watchlist + 股价 + 研究状态
  ├→ get_research_reminders() → >30天未研究的标的
  └→ 最近 5 个研究会话
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/v1/dashboard | 完整工作台数据 |
| GET | /api/v1/dashboard/brief | 最新晨间简报 |
| GET | /api/v1/dashboard/watchlist | 自选股概览 |

---

### 4.11 Portfolio — 投资组合（详细）

**数据模型** (`backend/portfolio/models.py`, schema `portfolio`)

```
Watchlist
├── id: UUID (PK)
├── name: String(256)
├── description: Text?
├── items: [WatchlistItem]
│   ├── ticker: String(16)
│   ├── notes: Text?
│   ├── target_price: Float?
│   ├── reason: Text?
│   └── priority: Int (1-5, default 3)
└── created_at

Holding
├── id: UUID (PK)
├── ticker: String(16)
├── shares: Float?
├── avg_cost_basis: Float?
├── sector: String(128)?
├── notes: Text?
├── is_active: Bool
└── created_at

InvestmentJournal
├── id: UUID (PK)
├── entry_type: String(16)      ← idea/analysis/reflection/lesson
├── ticker: String(16)?
├── title: String(256)
├── content: Text
├── tags: JSONB
└── research_session_id: UUID? (FK)
```

**API 端点**

| 方法 | 路径 | 说明 |
|------|------|------|
| POST/GET | /api/v1/portfolio/watchlists | 创建/列表自选股 |
| GET/PATCH/DELETE | /api/v1/portfolio/watchlists/{id} | 自选股 CRUD |
| POST | /api/v1/portfolio/watchlists/{id}/items | 添加自选项目 |
| DELETE | /api/v1/portfolio/watchlists/items/{id} | 移除项目 |
| POST/GET | /api/v1/portfolio/holdings | 创建/列表持仓 |
| PATCH | /api/v1/portfolio/holdings/{id} | 更新持仓 |
| POST | /api/v1/portfolio/holdings/{id}/close | 平仓 |
| POST/GET | /api/v1/portfolio/journal | 创建/列表投资日志 |
| GET | /api/v1/portfolio/journal/{id} | 日志详情 |

---

## 5. 核心基础设施

### 5.1 配置系统 (`backend/core/config.py`)

```python
class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "AI Research OS"
    APP_VERSION: str = "0.1.0"
    ENV: str = "development"

    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://airesearch:airesearch_dev@localhost:5432/airesearch"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # 向量
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str = "bge-m3:latest"
    EMBEDDING_DIMENSION: int = 1024

    # LLM
    LLM_PROVIDER: str = "deepseek"
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.deepseek.com"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Redis
    REDIS_URL: str = "redis://localhost:6380/0"
    REDIS_TTL: int = 3600

    # 文档
    UPLOAD_DIR: str = "data/uploads"
    MAX_UPLOAD_SIZE_MB: int = 50
    CHUNK_SIZE: int = 512
    CHUNK_OVERLAP: int = 64

    # 调度
    SCHEDULER_ENABLED: bool = True
    MARKET_DATA_SCHEDULE: str = "0 2 * * 1-5"
    REPORT_SCHEDULE: str = "0 6 * * 1-5"
    OBSERVATION_SCHEDULE: str = "30 5 * * 1-5"
```

### 5.2 事件系统 (`core/event_log.py` + `core/event_service.py`)

```
EventLog (schema: core)
├── source: String(32)        ← market/research/scheduler/ai/company
├── event_type: String(64)    ← prices.ingested/financials.ingested/research.completed/...
├── entity_type: String(32)   ← stock_price/financial_metric/research_session/...
├── entity_id: String(64)
├── actor: String(64)?
├── payload: JSONB            ← 事件详情
├── summary: String(256)?
└── occurred_at: DateTime

写操作 → EventLogger.record() → INSERT EventLog (只追加)
用于: 审计追踪 + Dashboard 聚合 + 时间线
```

### 5.3 调度器 (`core/scheduler.py` + `core/scheduler_jobs.py`)

基于 APScheduler (AsyncIOScheduler)，时区 Asia/Shanghai

```
3 个定时任务:
├── market_data_update (工作日 2:00)
│   → 遍历所有 active 公司的 ticker
│   → 调用 MarketService.get_prices() 拉取最新行情
│
├── morning_brief (工作日 6:00)
│   → 收集最新股价 + 未完成研究
│   → LLM 生成晨间简报
│   → 写入 EventLog
│
└── observation_cycle (工作日 5:30)
    → 检查自选股: 距上次研究>30天 → "need_research"
    → 检查股价: 波动>5% → 标记关注
    → 写入 EventLog
```

### 5.4 观察引擎 (`core/observation_engine.py`)

```
扫描自选股列表，产出观测:
├── 时间维度: 距上次研究 >14天 → "attention"
│              >30天 → "need_research"
├── 价格维度: 波动 >5% → 价格异动
└── 写入 EventLog (source="observation")
```

### 5.5 安全模块 (`core/security.py`)

```
JWT 认证 (HS256)
├── create_access_token(subject, expires_delta)
└── decode_access_token(token)

密码哈希 (bcrypt via passlib)
├── hash_password(password)
└── verify_password(password, hash)
```

### 5.6 异常体系 (`core/exceptions.py`)

```
AIResearchOSError (基类)
├── NotFoundError → 404
├── ValidationError → 422
├── ConfigurationError → 500
├── ExternalServiceError → 502
├── DocumentParsingError → 422
├── AuthenticationError → 401
├── AuthorizationError → 403
└── DuplicateError → 409
```

### 5.7 通用 CRUD (`core/crud.py`)

```python
CRUDBase[ModelT]
├── get(db, id) → ModelT | None
├── list(db, filters, skip, limit) → (items, total)
├── create(db, data) → ModelT
├── update(db, id, data) → ModelT
└── delete(db, id) → None
```

---

## 6. 数据流详解

### 5.1 数据流总图

```
外部数据源                        内部存储                    前端展示
┌────────────┐   采集    ┌──────────────┐   查询    ┌──────────────┐
│ akshare    │ ───────→ │ PostgreSQL   │ ←────── │ 行情中心     │
│ 腾讯源     │  Layer 2 │ StockPrice   │         │ K线图/财务   │
│ 新浪源     │          │ FinancialMetric│        │              │
│ 东财港股   │          │              │         │              │
└────────────┘          └──────────────┘         └──────────────┘
┌────────────┐   查询    ┌──────────────┐   查询    ┌──────────────┐
│ akshare    │ ───────→ │ PostgreSQL   │ ←────── │ 公司列表     │
| MySQL      |          │ Company      |         │ 公司详情     │
│ (本地3306) │          │ CompanyTag   │         │ 编辑/搜索    │
└────────────┘          └──────────────┘         └──────────────┘
┌────────────┐   嵌入    ┌──────────────┐   搜索    ┌──────────────┐
│ Ollama     │ ───────→ │ Qdrant/pgvec │ ←────── │ 知识库       │
│ BGE-M3     │ 向量化   │ 文档嵌入     │         │ 语义搜索     │
└────────────┘          └──────────────┘         └──────────────┘
┌────────────┐   调用    ┌──────────────┐   对话    ┌──────────────┐
│ DeepSeek   │ ←──────→ │ AI 服务      │ ←────── │ AI 中心      │
│ LLM API    │ 流式     │ Chat/Research│         │ 研究助手     │
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
     │  → 搜索 A股/港股/美股       │               │
     │  → 自动填充 ticker+name     │               │
     │               │              │               │
     │               ▼              ▼               ▼
     │          stock_profile_    Company +       ResearchSession
     │          cninfo (A) /      Thesis +        + TimelineEvent
     │          stock_hk_company_ Timeline
     │          profile_em (HK)
```

### 5.3 行情数据流

```
┌─────────┐   ┌──────────┐   ┌───────────┐   ┌──────────┐
│ 用户打开  │ → │ 搜索股票  │ → │ GET /market│ → │ 渲染 K线图│
│ 行情中心  │   │          │   │ /prices   │   │ (ECharts) │
└──────────┘   └──────────┘   └─────┬─────┘   └──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  get_prices()        │
                          │  1. 查 PostgreSQL    │
                          │     → 有数据 → 返回   │
                          │     → 无数据 ↓       │
                          │  2. A 股? → 查 MySQL  │
                          │     → 有数据 → 返回   │
                          │     → 无数据 ↓       │
                          │  3. 自动采集          │
                          │     → fetch via       │
                          │       akshare         │
                          │     → 写入 PG → 返回  │
                          └──────────────────────┘
                                     │
                           数据采集链路
                          ┌──────────▼──────────┐
                          │ _fetch_akshare()     │
                          │  Layer1: MySQL 本地库 │
                          │  Layer2: 腾讯/新浪源  │
                          │  Layer3: 云 MCP      │
                          └──────────────────────┘
```

### 5.4 财务数据流

```
┌──────────┐   ┌──────────────┐   ┌────────────┐
│ 财务 Tab  │ → │ GET /market  │ → │ 显示营收/  │
│ 点击      │   │ /financials  │   │ 净利润趋势 │
└──────────┘   └──────┬───────┘   └────────────┘
                       │
            ┌──────────▼──────────┐
            │ get_financials()     │
            │  A 股: → MySQL      │
            │  (stock_yjbb_em)    │
            │   → eps/revenue/    │
            │     net_income/     │
            │     op_margin       │
            │                     │
            │  港股: → akshare    │
            │  stock_financial_hk │
            │  _report_em         │
            │   → revenue/        │
            │     net_income/eps/ │
            │     gross_profit/   │
            │     operating_      │
            │     profit/rd_exp   │
            └─────────────────────┘
```

---

## 7. 行情数据链路

### 6.1 三层降级采集链

```
                     ┌─ Layer 1: MySQL (10ms) ─────────────────┐
                     │  AkshareMySQLAdapter                    │
                     │  host: 127.0.0.1:3306                  │
                     │  database: akshare                      │
                     │  表: stock_zh_a_hist (日K线)            │
                     │      stock_yjbb_em (财务指标)           │
                     │      stock_name_entity (名称映射)        │
                     │  → 覆盖约 37 只 A 股                     │
                     └────────────────────────────────────────┘
                                ↓ 无数据
                     ┌─ Layer 2: 本地 akshare (3-10s) ─────────┐
                     │  _fetch_akshare_local()                  │
                     │  → uv run --directory akshare_mcp        │
                     │        python -c "akshare.code()"        │
                     │                                         │
                     │  A 股: stock_zh_a_hist_tx (腾讯源)        │
                     │  港股: stock_hk_daily (新浪源)            │
                     │  财务: stock_financial_hk_report_em      │
                     │        (东财港股API)                     │
                     │  → 覆盖任意 A 股 + 港股                   │
                     └────────────────────────────────────────┘
                                ↓ 无数据
                     ┌─ Layer 3: 云 MCP (1-3s) ────────────────┐
                     │  8.137.104.120:8088/mcp                 │
                     │  通过 MCP ClientSession 调用             │
                     │  → 备用 (可能同网段被屏蔽)                │
                     └────────────────────────────────────────┘
                                ↓ 全失败
                          返回 [] (空)
```

### 6.2 价格数据采集流程

```
POST /market/prices/{ticker}/ingest
  │
  ├→ fetch_and_store_prices()
  │   │
  │   └→ _fetch_akshare(ticker)
  │       ├→ Layer 1: MySQL → 有数据? → return
  │       ├→ Layer 2: 本地 ak → 有数据? → return
  │       └→ Layer 3: 云 MCP → 有数据? → return
  │
  └→ upsert_prices(ticker, prices)
      ├→ 逐行检查 PostgreSQL 是否已存在
      ├→ 不存在则 INSERT StockPrice
      └→ flush → 记录 event log
```

### 6.3 前端聚合

```
日K → 原始数据 (API 返回最新在前, StockChart 自动逆序)
周K → aggregateOHLC(prices, "weekly")
月K → aggregateOHLC(prices, "monthly")
      按 ISO 周/月分组:
      open = 第一根 bar 的 open
      close = 最后一根 bar 的 close
      high = 期间最高
      low = 期间最低
      volume = 期间总和
```

### 6.4 股票搜索数据流

```
GET /market/search?query=xxx
  │
  ├→ PostgreSQL companies 表
  │   → Company.ticker ILIKE %query%
  │   → Company.name ILIKE %query%
  │
  └→ MySQL akshare stock_name_entity
      → symbol LIKE %query%
      → stock_name LIKE %query%
  │
  └→ 合并去重 (由 ticker symbol 去重)
  │
  → 返回 [{symbol, name}] 最多 20 条
```

---

## 8. AI 能力

### 7.1 嵌入模型

```
                 ┌─────────────────────┐
                 │  create_embedding()  │
                 │  core/adapters/      │
                 │  embedding.py        │
                 └──────────┬──────────┘
                            │
              ┌─────────────▼─────────────┐
              │ EMBEDDING_PROVIDER =      │
              │ "ollama" (默认)           │
              │                           │
              │ 1. OllamaEmbedding        │
              │    → Ollama BGE-M3        │
              │    → http://local:11434   │
              │    → 768 维向量            │
              │                           │
              │ 2. SentenceTransformer    │
              │    (offline fallback)     │
              │    → HF_HUB_OFFLINE=1     │
              │    → 国内不可用             │
              └───────────────────────────┘
```

### 7.2 LLM 对话

```
POST /ai/chat { messages, stream: true }
  │
  ├→ 从配置读取 LLM_PROVIDER / LLM_MODEL
  ├→ 调用 DeepSeek API (流式 SSE)
  │   → 支持知识库上下文注入 (RAG)
  └→ 流式返回给前端
```

---

## 9. 数据库与存储

### 8.1 PostgreSQL (主数据库)

Schema: `public` (默认) + `company` (公司模块专用)

| 表 | Schema | 用途 |
|----|--------|------|
| companies | company | 公司信息 |
| company_tags | company | 公司标签 |
| stock_prices | public | 日K线数据 |
| financial_metrics | public | 财务指标 |
| documents | public | 文档元数据 |
| research_sessions | public | 研究会话 |
| timeline_events | public | 研究时间线 |
| portfolios | public | 投资组合 |
| portfolio_holdings | public | 持仓记录 |
| events | public | 事件日志 |

### 8.2 MySQL (外部 akshare 行情库)

| 表 | 用途 |
|----|------|
| stock_zh_a_hist | A 股日 K 线 |
| stock_yjbb_em | A 股财务指标 |
| stock_value_em | A 股估值 (PE/PB) |
| stock_name_entity | A 股代码-名称映射 |

### 8.3 Qdrant (向量数据库)

存储文档嵌入向量，用于语义搜索。

### 8.4 Redis (缓存)

用于缓存和任务队列。

---

## 10. 前端路由与组件

### 9.1 页面路由

| 路径 | 页面 | 说明 |
|------|------|------|
| `/` | 工作台 | 总览仪表盘 |
| `/companies` | 公司中心 | 公司列表+创建+编辑+删除 |
| `/companies/[id]` | 公司详情 | 概览/观点/财务/研究/文档 Tab |
| `/market` | 行情中心 | 搜索+K线图+财务图表 |
| `/research` | 研究中心 | 研究会话列表 |
| `/research/quick` | 快速研究 | 输入 ticker+问题→AI 分析 |
| `/research/timeline` | 研究时间线 | 按时间轴展示研究过程 |
| `/research/[id]` | 研究详情 | 单次研究会话详情 |
| `/documents` | 文档管理 | 上传/查看/删除文档 |
| `/knowledge` | 知识库 | 搜索文档片段 |
| `/ai` | AI 中心 | AI 对话界面 |
| `/portfolio` | 投资组合 | 组合+持仓管理 |
| `/system` | 系统状态 | 系统运行状态 |

### 9.2 共享组件

| 组件 | 路径 | 用途 |
|------|------|------|
| StockChart | components/StockChart.tsx | ECharts K 线图 (MA5/MA20/成交量/dataZoom) |
| (内联) MiniBar | market/page.tsx, companies/[id]/page.tsx | 财务柱状图 |

### 9.3 API 钩子 (`frontend/src/lib/api.ts`)

| 钩子 | 端点 | 用途 |
|------|------|------|
| useGet / useList | 通用 | GET 请求封装 |
| useCreate | 通用 | POST 请求封装 |
| useCompany | /companies/{id} | 公司详情 |
| useCompanies | /companies | 公司列表 |
| useCompanyWorkspace | /companies/by-ticker/{ticker}/workspace | 公司工作区 |
| useMarketPrices | /market/prices/{ticker} | K 线数据 |
| useFinancialMetrics | /market/financials/{ticker} | 财务指标 |
| useStockSearch | /market/search | 股票搜索 |
| useDocuments | /documents | 文档列表 |
| useResearchSessions | /research/sessions | 研究会话 |
| useUpdateThesis | /companies/by-ticker/{ticker}/thesis | 更新观点 |

---

## 11. 开发与部署

### 10.1 启动流程

```bash
# 1. 启动基础设施 (PostgreSQL + Qdrant + Redis)
docker compose -f docker/docker-compose.yml up -d

# 2. 清除代理 (socks 代理会干扰本地服务)
export no_proxy="localhost,127.0.0.0/8,::1"

# 3. 启动后端
cd backend && ALL_PROXY= all_proxy= PYTHONPATH=. uvicorn api.app:app --reload --host 0.0.0.0 --port 8000

# 4. 启动前端
cd frontend && npm run dev

# Makefile 一键启动
make dev        # 全部启动
make dev-db     # 仅数据库
make migrate   # 运行迁移
```

### 10.2 已知问题

1. **SOCKS 代理** — `all_proxy=socks://...` 会干扰 Qdrant httpx 客户端和 akshare 本地子进程，需 `ALL_PROXY= all_proxy=` 前缀
2. **东方财富 API 屏蔽** — `stock_zh_a_hist()` (eastmoney) 在当前环境下被 IP 封锁，改用腾讯源 `stock_zh_a_hist_tx()`
3. **HuggingFace 无法访问** — `HF_HUB_OFFLINE=1` 强制离线，sentence-transformers fallback 不可用
4. **SQLAlchemy selectinload** — `research/timeline.py` 中 `selectinload().order_by()` 不兼容，用 Python 排序代替
5. **异步任务** — `research/quick.py` 的 POST 处理器同步跑研究链，会导致前端代理超时，需重构为后台任务

---

## 附: 关键配置

```python
# backend/core/config.py
class Settings(BaseSettings):
    # 数据库
    DATABASE_URL: str = "postgresql+asyncpg://airesearch:airesearch_dev@localhost:5432/airesearch"
    REDIS_URL: str = "redis://localhost:6380/0"

    # LLM
    LLM_PROVIDER: str = "deepseek"
    LLM_MODEL: str = "deepseek-chat"
    LLM_API_KEY: str = ""
    LLM_API_BASE: str = "https://api.deepseek.com"

    # 嵌入模型
    EMBEDDING_PROVIDER: str = "ollama"
    EMBEDDING_MODEL: str = "bge-m3:latest"
    OLLAMA_BASE_URL: str = "http://localhost:11434"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
```

```javascript
// frontend/next.config.js
// API 代理 /api/* → http://localhost:8000/api/v1/*
```

---

> 本文档由 Claude Code 自动生成，基于对项目代码的全面分析。
