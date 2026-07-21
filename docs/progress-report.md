# AI Research OS — 项目完整进度报告

**生成时间**: 2026-07-21 | **状态**: V1 核心功能已完成

---

## 一、项目定位

个人 AI 驱动的投资研究助手。核心理念：**"Research First, not AI First"** — AI 是研究流程中的能力组件，而非中心。

**已验证的核心闭环：**
```
创建研究 → AI 生成计划(6子问题/6维度) → 收集证据(知识库+行情)
  → AI 生成报告 → 完结(观点/决策/置信度)
```

---

## 二、关键指标

| 指标 | 数值 |
|------|------|
| 后端代码 | ~7300 行 Python |
| 前端代码 | ~2450 行 TSX/TS |
| 数据库 | 7 schema × 17 张表 |
| 同步测试 | 88 个 |
| 异步测试 | 10 个（需 bge-m3 模型） |
| 种子数据 | 8 公司 + 2年合成行情 + 1 研究会话 |
| Git commits | 19 |
| GitHub | `FromZero2One/ai_research_OS.git`（main）|

---

## 三、Phase 完成状态

```
Phase 1 基础工程: ████████████████ 100%  ✅
Phase 2 文档管道:  ████████████████ 100%  ✅
Phase 3 Research:  ████████████████ 100%  ✅
Phase 4 产品化界面: ████████████████ 100%  ✅
Phase 5 自动化:    ████████████████ 100%  ✅
```

---

## 四、✅ 已完成的全部功能

### 4.1 Core Layer（核心层）

| 组件 | 文件 | 行数 | 说明 |
|------|------|------|------|
| 配置管理 | `core/config.py` | 77 | pydantic-settings 全面配置 |
| 数据库 | `core/database.py` | 39 | 异步 SQLAlchemy + get_db 依赖注入 |
| 接口协议 | `core/interfaces.py` | 161 | 6 个 Protocol（Embedding/VectorStore/LLM/DocumentParser/MarketData/Cache） |
| 异常体系 | `core/exceptions.py` | 44 | NotFound/Validation/Duplicate/Auth/External |
| 安全模块 | `core/security.py` | 42 | 基础安全工具 |
| Event Log | `core/event_log.py` | 30 | 写一次审计日志模型 |
| Event 服务 | `core/event_service.py` | 39 | EventLogger 写入封装 |

**适配器（`core/adapters/`）：**

| 适配器 | 行数 | 说明 |
|--------|------|------|
| `llm.py` | 133 | Ollama + OpenAI 双适配器 |
| `vector_store.py` | 90 | Qdrant CRUD（AsyncQdrantClient） |
| `embedding.py` | 46 | Sentence-Transformers / BGE-M3 |
| `pdf_parser.py` | 187 | PyMuPDF 解析，加密/扫描件检测，页元数据 |
| `reranker.py` | 82 | BGE Reranker（cross-encoder） |
| `cache.py` | 63 | 缓存适配器 |
| `akshare_mysql.py` | 261 | AKShare MySQL 数据源 |

### 4.2 Company Center（公司中心）

- 公司 CRUD + 搜索 + 标签管理
- 8 家公司种子数据（AAPL/MSFT/GOOGL/AMZN/NVDA/TSLA/JPM/BRK.B）
- 前端公司详情页：Tab 布局（概览/财务/研究/文档）、K 线图、营收利润趋势

### 4.3 Market Center（行情中心）

- 8 家公司 × 2 年合成日度行情数据
- 财务指标表（营收/利润/利润率/EPS）
- 行情 API（价格/财务/搜索/信息）
- 前端行情页面：ECharts K 线、快速切换股票、时间范围选择、统计卡片

### 4.4 Document Center（文档中心）

- 文档上传 API（PDF/MD/TXT/HTML，文件类型+大小校验）
- PDF 解析管道：结构化文本 + 逐页元数据 + 加密/扫描件检测
- 文本切片：三段式策略（段落→句子→词边界），512 分块/64 重叠
- Embedding + Qdrant 索引（document_id/chunk_index/元数据）
- 前端拖拽上传页面（含进度）

### 4.5 Knowledge Center（知识中心）

- **Dense 检索**: Qdrant 向量搜索（BGE-M3 embedding）
- **Sparse 检索**: BM25（rank_bm25）
- **RRF 融合**: Reciprocal Rank Fusion
- **BGE Reranker**: Cross-encoder 重排序
- 前端搜索页面（类型过滤/得分条/展开）

### 4.6 AI Center（AI 中心）

- Prompt 模板 CRUD（系统提示/用户模板/模型/temperature/输出 Schema）
- AI 生成（模板变量插值执行）
- 文本摘要 + 结构化提取
- AI 工作流（多步骤 DAG：LLM 步骤 + 转换步骤）
- 前端 AI 管理页面
- 8 个 API 端点

### 4.7 Research Center（研究中心）

| 功能 | 说明 |
|------|------|
| **Research Planner** | LLM 自动生成研究计划（6 子问题/6 维度/数据需求），含 JSON 解析+降级方案 |
| **Evidence Collector** | 自动从知识库+市场数据收集证据，支持/反对/中性分类 |
| **AI 报告生成** | 结构化 6 段报告（执行摘要/关键发现/维度分析/风险/证据平衡/结论） |
| **状态机** | draft → researching → reviewing → completed → archived，三层强制 |
| **Event Log** | 7 种事件追踪（started/plan_generated/状态变更/evidence_added/report_created/completed） |

- 前端研究工作流：操作按钮、计划展示、证据分组、报告预览、完结流程

### 4.8 Portfolio Center（投资组合中心）

- 自选列表 CRUD
- 自选项目管理
- 持仓管理（添加/查看/平仓）
- 投资日志
- 前端管理页面

### 4.9 自动化（Scheduler）

| 组件 | 说明 |
|------|------|
| **APScheduler 框架** | AsyncIOScheduler + CronTrigger，作业注册表，启停/状态上报 |
| **市场数据更新** | 工作日 2am 自动拉取所有公司行情 |
| **Morning Brief** | 工作日 6am AI 生成晨间简报（市场数据+开放研究+LLM） |
| **调度 API** | `GET /scheduler/status`、`POST /scheduler/run/{name}` |

### 4.10 前端（8 个页面）

| 页面 | 路由 | 核心功能 |
|------|------|---------|
| 首页 | `/` | 概览 |
| 研究 | `/research` | 研究工作流（计划/证据/报告/完结） |
| 公司 | `/companies` | K 线图/营收利润趋势/关联研究文档 |
| 文档 | `/documents` | 拖拽上传/进度 |
| 知识 | `/knowledge` | 混合搜索/类型过滤/得分条 |
| 行情 | `/market` | ECharts K 线/快速切换/时间范围 |
| AI 中心 | `/ai` | Prompt 模板/摘要管理 |
| 投资组合 | `/portfolio` | 自选/持仓/日志 |

### 4.11 技术栈

| 层 | 技术 |
|----|------|
| Backend | Python / FastAPI / SQLAlchemy / Alembic |
| AI | Ollama / OpenAI（双适配器）/ LangGraph-ready |
| Knowledge | Qdrant / BGE-M3 / BGE-Reranker / BM25 |
| Database | PostgreSQL（pgvector）/ Redis |
| Frontend | Next.js 15 / React 19 / TypeScript / Tailwind 4 / ECharts 6 |
| Deployment | Docker Compose |

---

## 五、❌ 尚未完成

### 5.1 已知问题

| # | 问题 | 说明 | 影响 |
|---|------|------|------|
| 1 | `all_proxy=socks://...` 环境变量破坏 Qdrant httpx 客户端 | 需 `ALL_PROXY=` 前缀 | 开发环境配置 |
| 2 | `sentence-transformers` 未安装 | 需 ~2.2GB 下载 | Embedding 管道无法本地运行 |
| 3 | 无单元测试 | `backend/tests/` 只有集成测试 | 缺少细粒度覆盖 |

### 5.2 可选后续项目

| 项目 | 预计 | 说明 | 优先级 |
|------|------|------|--------|
| 用户系统（注册/登录/JWT） | ~3 天 | 当前无用户认证，所有操作匿名 | 低 |
| bge-m3 模型下载 + 异步测试通过 | ~半天 | 需下载 ~2.2GB 模型，10 个异步测试可运行 | 低 |
| RAG 溯源增强（页码引用） | ~1 天 | 搜索结果带具体引用位置 | 低 |
| CI/CD（GitHub Actions） | ~2 天 | 自动测试+部署流水线 | 低 |
| 生产部署文档 | ~半天 | 生产环境部署指南 | 低 |
| 单元测试 | 未评估 | 补充细粒度单元测试 | 低 |

### 5.3 V2 规划方向

| 领域 | V1（当前） | V2（待启动） |
|------|-----------|------------|
| Knowledge | Hybrid RAG | + Knowledge Graph |
| AI | Single LLM calls | + LangGraph DAGs |
| Portfolio | Watchlist + Journal | + P&L Tracking |
| Research | Manual + Assist | + Auto Research |
| 新增 | — | + 交易信号（V3 目标） |

---

## 六、架构概览

```
                    User
                     │
              Research Workspace
              (Next.js Dashboard)
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

**依赖规则**: 依赖单向向上。Research 可调用 Knowledge；Knowledge 不能调用 Research。

### 模块结构规范

每个模块遵循统一结构：

```
module/
├── models.py    # SQLAlchemy ORM 模型
├── schemas.py   # Pydantic 请求/响应 Schema
├── service.py   # 业务逻辑
└── routes.py    # FastAPI 路由
```

---

## 七、数据流

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

---

## 八、开发命令

| 命令 | 说明 |
|------|------|
| `make dev` | 启动完整开发环境 |
| `make dev-db` | 启动 Docker 基础设施 |
| `make dev-backend` | 启动 FastAPI（:8000） |
| `make dev-frontend` | 启动 Next.js（:3000） |
| `make test` | 运行测试 |
| `make lint` | 代码检查 |
| `make format` | 自动格式化 |
| `make migrate` | 运行数据库迁移 |
| `make ingest-sample` | 导入种子数据 |
| `make reset-db` | 重建数据库 |
