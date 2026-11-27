# AI Research OS

> **Screener First, not AI First** — 数据与规则管筛选，运行链路全系统零 LLM（仅 Ollama embedding 保留）。

一个个人 AI 价值投资筛选器：行情/财务数据 + 年报知识库 → 预设量化初筛 → 事实检查确定性判定 → **每日自动产出 Markdown 价值推荐清单（股票 + 理由）**。运行链路零 LLM，单轮 ≤2 分钟。

> **2026-11-24 项目瘦身**：已删除研究中心（research）、投资组合（portfolio）、AI 中心（prompt 模板）、仪表盘（dashboard）四个模块的代码，聚焦价值筛选核心链路。数据库表与迁移历史保留（回捡请 `git revert`）。裁剪设计见 `docs/superpowers/specs/2026-11-24-slim-to-value-screener-design.md`。
>
> **2026-11-25 二次瘦身（价值推荐聚焦）**：删除组合构建/再平衡、推荐后表现跟踪与快照、回测交互路由（回测引擎保留为脚本 `tools/run_backtest_queue.py`）、freeform 自由文本模式（预设为唯一运行入口）、运行取消、近似命中；预设只读化；新增事实检查确定性化 `screener/fact_checks.py`（审计意见/诉讼/现金覆盖三检查器，LLM 只判叙事标准）；报告改为四段投资理由结构；新增 `GET /api/v1/screener/latest-report`；前端收缩为价值推荐清单视图。设计见 `docs/superpowers/specs/2026-11-24-slim-to-value-recommendation-design.md`。
>
> **2026-11-25 三次简化（深判退役）**：LLM 深判整体退役（叙事标准不再进入执行路径）、变化日报/失败告警 Webhook 全删、回测去框架化（脚本直调纯函数落 JSON）、死端点清理（CSV 导出/自选推送）、历史排查脚本归档 `backend/tools/archive/`。运行链路 = compose → 确定性初筛 + fact_checks → 三段报告 → `latest-report`，零 LLM 依赖（知识库问答除外）。设计见 `docs/superpowers/specs/2026-11-25-llm-retire-simplify-design.md`。
>
> **2026-11-26 六次简化**：知识库问答退役（删 `/knowledge/ask`、`/knowledge/llm/models` 与 `core/adapters/llm.py`、`core/llm_usage.py`，全系统零 LLM，仅 Ollama embedding 保留）；公司中心退役（删 CRUD/thesis/watch API 与前端公司页，仅保留 `GET /companies` 供文档中心「关联公司」下拉）；删 `market/service/news_service.py` 与 `ScreenerBacktestRun` ORM 类（表保留）；券商口径修复（cash_coverage 支持 `exempt_financial_type` 豁免）；报告新增「较上一轮」轮次对比；confidence 字段退役（列保留恒空）；8 内置预设带证据分层元数据（`PRESET_EVIDENCE`），`SCREENER_SCHEDULE_PRESETS` 默认改 `financial,value`。

## 文档

- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — 架构文档（模块、依赖规则、Screener 流水线、数据架构）
- **[USAGE.md](USAGE.md)** — 使用手册（启动、功能模块详解、FAQ）
- **[backend/README.md](backend/README.md)** — 后端开发文档（数据库、API、配置、AI、测试）
- **[frontend/README.md](frontend/README.md)** — 前端开发文档（技术栈、目录、类型生成）

## Architecture

```text
                User
                 │
          Screener Workspace
          (Vue 3 Dashboard)
                 │
                 ▼
          API Gateway (FastAPI)
                 │
  ┌──────────────────────────────────────┐
  │          Application Layer           │
  ├──────────────────────────────────────┤
  │  Market   │  Document                │
  │  Center   │  Center                  │
  │           │  ├───────────────────────┤
  │           │  │  Knowledge Center(RAG)│
  │           │  ├───────────────────────┤
  │           │  │  Screener 确定性筛选   │
  └──────────────────────────────────────┘
                 │
  ┌──────────────────────────────────────┐
  │             Core Layer               │
  ├──────────────────────────────────────┤
  │  DB │ Vector │ Embedding │ Cache │ Scheduler│
  └──────────────────────────────────────┘
```

> **数据源架构**：A 股/港股统一走 akshare 子进程直连（Tencent/Sina/Eastmoney），数据落 PG（`market` schema）；美股走 yfinance（需代理）。日常行情/财务无外部 MySQL 依赖；仅预设回测可选读取外部 MySQL 历史前复权日线（`BACKTEST_MYSQL_URL`，未配置时回测不可用）。

## 核心链路

| 模块 | 职责 | Tech |
|--------|---------------|------|
| **Market Center** | 股价、财务、估值、比率层（无分析） | yfinance / AKShare |
| **Document Center** | 上传 → 解析 → 切片 → 嵌入 → 索引（年报 PDF 表格结构化）；仅保留 `GET /companies` 供「关联公司」下拉（Company 表与 ORM 保留，screener 数据质量统计/market search 仍读） | PyMuPDF + pdfplumber + BGE-M3 |
| **Knowledge Center** | 混合 RAG：稠密 + 稀疏 + 重排——事实检查证据来源（知识库问答已退役） | Qdrant + BM25 + RRF + BGE Reranker |
| **Screener** | 42 指标 + 8 内置预设选股（预设只读、唯一运行入口）、确定性初筛 + 事实检查三检查器（审计意见/诉讼/现金覆盖，券商口径豁免）、三段报告 + 轮次对比、`latest-report` 报告指针；无 LLM、无 Webhook、无 CSV 导出 | AKShare 纯确定性 |

> **Screener 数据管道（2026-10-22）**：全市场快照走新浪源（东财风控应对）；财务三表（业绩/资产负债/现金流）均为市场级一次调用（~5000 只/期），不再逐只拉取；流动/速动/周转/成长率走东财 F10 主要指标（`RPT_F10_FINANCE_MAINFINADATA`）分页补采。已知缺口见 Roadmap。

## Data Flow

```text
Market (股票池)
  ↓
Document (年报)
  ↓
Knowledge (混合 RAG — 事实检查证据)
  ↓
Screener (量化初筛 → 事实检查确定性判定 → 报告)
  ↓
Markdown 价值推荐清单（三段：量化筛选 / 事实检查 / 不推荐与存疑原因）
```

> 公司中心已退役（2026-11-26）：自选/Thesis/CRUD 删除，仅保留 `GET /companies` 供文档中心「关联公司」下拉；Company 表保留（screener 数据质量统计、market search/profile/freshness、document.company_id 外键仍读）。

**Dependency rule**: Dependencies go UP only. Screener can call Knowledge; Knowledge cannot call Screener.

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

> **LLM config**: 全系统零 LLM（2026-11-25 深判退役 + 2026-11-26 知识库问答退役）；仅 embedding 走 Ollama（`OLLAMA_EMBEDDING_MODEL`）。无需再配置 `OPENAI_API_KEY` 等任何 LLM 变量。

Visit **http://localhost:5173** — the Screener workspace（价值推荐清单视图）.

## 当前进度

| 模块 | 完成度 | 备注 |
|------|:---:|------|
| 公司中心 | 已退役 | CRUD/Thesis/自选已删除，仅 `GET /companies` 供文档「关联公司」下拉；Company 表保留 |
| 市场中心 | ~90% | A股行情/财务/估值 akshare 直连全链路 + 数据覆盖矩阵（含量性维度）+ 比率层 + PE/PB 历史分位；美股 yfinance 备选 |
| 文档中心 | ~90% | 后台异步索引、PDF 表格结构化、切片内容类型打标、关联公司；OCR 待 V2 |
| 知识中心 | ~90% | 混合 RAG + Reranker + 内容类型过滤（知识库问答已退役） |
| 智能选股 | ~97% | 42 指标（TTM 估值 + 现金流质量 + 因子深度 + 银行/保险专属）+ 8 内置预设（只读）；股票池卫生 + 行业隔离/相对排名；确定性初筛 + 事实检查三检查器（`fact_checks.py`：审计意见/诉讼/现金覆盖）；报告三段结构 + `latest-report` 指针；运行链路零 LLM（单轮 ≤2 分钟）；定时筛选 + 调度状态/立即运行；财务数据工作日定时更新 |

> 已删除模块（2026-11-24）：研究中心、投资组合、AI 中心（Prompt 模板）、仪表盘——数据库表保留，详见文首瘦身说明。2026-11-25 二次瘦身再删除：组合/再平衡、表现跟踪/快照、回测交互路由（引擎保留为脚本）、freeform 模式、运行取消、近似命中。三次简化再删除：LLM 深判（judge/judge_eval/eval 目录）、diff/notify/Webhook、回测 service 层（backtest_service/backtest_report）、CSV 导出与自选推送端点。2026-11-26 六次简化再删除：知识库问答、公司中心前端与大部分 API、`news_service.py`、`ScreenerBacktestRun` ORM 类、confidence 字段。

### 智能选股评估快照（2026-10-25）

数据底座：行情 5,313 只 / 1,137 万行（主板 2,111 只全覆盖）；财务 15 期 × 32 指标；知识库 103 份年报 / 55,135 切片。

5 年回测（15 期，基准 −4.56%）：**金融价值 +6.89%（超额 +11.45%，3 年/5 年一致）** > 深度价值 +5.60% > 周期反转 −0.87% > 高成长 −6.90% > 核心资产 −14.92% > GARP −23.61%。

实时判定（2026-11-25 深判退役前留存）：高成长 15/46 推荐（可作候选池，部分证据偏软）、金融价值 2/10（杭州银行、青岛银行，证据为年报硬指标）、深度价值 0/50（定性标准属事实性检查，LLM 判不了——现已改为确定性判定）。

判定链路（现口径）：确定性初筛（量化规则）→ 事实检查三检查器（审计意见/诉讼/现金覆盖，`fact_checks.py`）→ 确定性判定落 `ScreenerJudgement`（历史明细仍可查）→ 三段报告。历史评估快照中的深判数据仅作存档。详见 [backend/README.md](backend/README.md)「选股数据底座与预设评估」。

总体：后端测试随两次瘦身删除了 research/portfolio/ai 及组合/表现/取消/近似命中相关用例；前端 vue-tsc/build 通过（2026-11-25 二次瘦身后验证）。改动文件 ruff 通过（仓库仍保留历史 E501 债务）。
已知缺口：①知识库已入库 103 份年报（55,135 切片），事实性标准（审计意见/诉讼/现金覆盖）走 `fact_checks.py` 确定性判定，叙事类标准已随深判退役不再进入执行路径；②回测为脚本直调纯函数（`tools/run_backtest_queue.py`，需 `BACKTEST_MYSQL_URL`，结果落 JSON），service 层已删除；③行情已覆盖主板 2,111/2,111、全库 5,313 只；④`valuation_history` 为空且上游 `stock_a_indicator_lg` 本机无数据，估值历史分位暂未接入选股。其余历史缺口见 [memory/ai-research-os-session.md](memory/ai-research-os-session.md)。

## API (when backend is running)

后端 API 前缀统一为 `/api/v1`，交互式文档见 http://localhost:8000/docs；接口速查见 [backend/README.md](backend/README.md)。

## Key Design Decisions

1. **No Knowledge Graph** — V2 upgrade path, not V1 complexity
2. **No LlamaIndex** — Hand-rolled SentenceTransformer + Qdrant for control
3. **No Trading Agents** — V2 feature, not now
4. **Event Log** — Write-once audit trail for process traceability
5. **Core Layer = Interfaces, not Implementations** — Protocols > concrete classes
6. **Screener First** — 2026-11-24 瘦身后首页即智能选股；数据/规则管筛选与判定，全系统零 LLM（仅 embedding 走本地模型）
7. ~~**AI = Capability, not Center**~~ — LLM 已全面退役（2026-11-25 深判退役、2026-11-26 知识库问答退役）
8. ~~**自选列表并入公司中心**~~ — 公司中心已退役（2026-11-26），自选/Thesis 功能随之删除
9. **文档表格结构化** — 财报类 PDF 表格按词坐标重建为 Markdown（保留集团/母公司列组），整块入库、问答不丢列含义

## Security Boundary

> **设计决策：本项目定位为单用户本地工具，API 默认不启用认证。** 请勿直接暴露到公网。

- 路由层未接入 JWT 认证（`core/security.py` 提供工具但未被使用）——这是有意的 V1 决策，不是疏漏
- `SECRET_KEY` 默认每次启动随机生成；若需跨重启保持 token 有效，请在 `backend/.env` 中显式设置
- CORS 默认仅允许 `http://localhost:5173`（开发前端），按需在 `.env` 中扩展
- 若未来需要部署到服务器/公网，第一优先级是接入认证（复用 `core/security.py`）并收紧基础设施访问

## Roadmap

已明确放弃：multi-agent、trading agents、LangGraph DAG 工作流（单用户工具过度设计）；2026-11-24 进一步删除研究中心/投资组合/AI 中心/仪表盘，聚焦价值筛选。

核心数据分工原则（2026-10-14）：**接口管"数"，PDF 管"事"** — Market 中心是数字唯一事实源；文档链路管定性正文（MD&A/风险/附注/公告）。

当前方向（分析师优先级排序）：

| 方向 | 状态 | 内容 |
|---|---|---|
| ~~数据质量看板~~ | ✅ | 覆盖矩阵 `GET /market/freshness/coverage` + Market 页卡片 |
| ~~比率层 + 历史分位~~ | ⚰️ 2026-11-26 退役 | 曾经：`market/ratio_service.py` 派生比率 + PE/PB 历史分位（`/market/ratios*`）。整链零消费（CompanyDetail 卡片随公司中心退役），已随七次简化删除；`valuation_history` 表保留 |
| ~~覆盖矩阵定性维度~~ | ✅ 2026-10-15 | 矩阵新增定性列：已索引文档含 mda/risk 切片 → ok；仅已索引 → partial；无 → missing；纳入 worst_health |
| ~~预设标准库（Screener v1.5）~~ | ✅ 2026-10-24 | 42 指标（TTM 估值 + 现金流质量 + 因子深度 + 银行/保险专属）+ 8 内置预设（含银行/保险价值）+ 组合模式；股票池卫生；申万行业分类与金融行业隔离；回测风险指标（Sharpe/Sortino/Calmar/年化超额） |
| ~~项目瘦身聚焦价值筛选~~ | ✅ 2026-11-24 | 删除 research/portfolio/ai/dashboard 四模块代码，数据库表保留；文档同步更新 |
| ~~二次瘦身：价值推荐聚焦~~ | ✅ 2026-11-25 | 删组合/再平衡、表现跟踪/快照、回测交互路由（引擎保留为脚本）、freeform 模式、运行取消、近似命中；预设只读化；新增 `fact_checks.py` 确定性事实检查、报告四段投资理由结构、`GET /screener/latest-report`；前端收缩为价值推荐清单视图 |
| ~~三次简化：深判退役~~ | ✅ 2026-11-25 | 删 LLM 深判（judge/eval）、diff/notify/Webhook、回测 service 层、CSV 导出与自选推送端点；报告改三段（量化筛选/事实检查/不推荐与存疑原因）；运行链路零 LLM、单轮 ≤2 分钟；历史排查脚本归档 `backend/tools/archive/` |
| ~~六次简化：问答与公司中心退役~~ | ✅ 2026-11-26 | 删知识库问答（全系统零 LLM，仅 embedding 保留）、公司中心（仅留 `GET /companies`）、`news_service.py`、`ScreenerBacktestRun` ORM 类（表保留）、confidence 字段（列保留恒空）；cash_coverage 券商口径豁免（exempt）；报告新增「较上一轮」轮次对比；预设证据分层（`PRESET_EVIDENCE`）；`SCREENER_SCHEDULE_PRESETS` 默认改 `financial,value` |
| ~~七次简化：infra 退役与死链清理~~ | ✅ 2026-11-26 | 删 task_manager 持久任务队列（后台协程直跑）、事件查询/清理 API、比率层+估值分位整链、profile 摄取链、company_tags 空壳、openapi.json 生成链、Makefile 坏目标；测试假向量化解耦 Ollama（豁免清单收窄至 4 个日期依赖类） |

收尾待办（小项）：Market.vue 覆盖网格列数动态化（当前硬编码 `repeat(5, 90px)`）；test_finalize_session 补 LLM mock（真实 LLM 调用挂起）；qualColor 硬编码色值统一 CSS 变量。

Screener 后续（2026-10-22 排序）：

1. ~~财务数据更新调度~~ ✅ 2026-10-24 — `core/financial_sync.py` 挂 APScheduler（`FINANCIAL_DATA_SCHEDULE`，工作日 3:15），三类数据源 SAVEPOINT 隔离，`/scheduler/status` 可见
2. ~~全链路真实端到端验证~~ ✅ 2026-10-22 — 深度价值 50 候选/21 推荐；高成长 106 候选（营收/净利同比规则生效）；F10 指标覆盖 98%+
3. ~~预设回测~~ ✅ 2026-10-23 — MVP 已交付：`POST /screener/backtests`（5 年季度调仓、外部 MySQL 前复权日线、akshare 历史财务按需补拉、年报口径无未来函数、近似市值声明）；结果 {summary, yearly} + Markdown 报告落盘；见 `backend/screener/backtest*.py`
4. ~~报告数据时效标注~~ ✅ 2026-10-22 — 报告概览标注「财务数据截至 2026Q2（2026-06-30）」
5. **数据源去单点** — 财务/新闻仍依赖东财；外部 MySQL（8.137.104.120，缺财务三表）可升级为首选源，akshare 降为兜底
