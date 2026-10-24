# AI Research OS — Backend

Python/FastAPI 后端。完整使用手册见根目录 [`USAGE.md`](../USAGE.md)。

## 技术栈

- **框架**: FastAPI + async SQLAlchemy + Pydantic v2
- **存储**: PostgreSQL（多 schema + pgvector）+ Qdrant（向量）+ Redis（缓存）
- **AI**: DeepSeek（OpenAI 兼容，本机默认）/ Ollama（本地 LLM + Embedding）
- **数据源**: akshare 子进程直连（A股/港股，Tencent/Sina/Eastmoney），yfinance（美股备选）
- **质量**: pytest 390+ 用例 + ruff + mypy + pre-commit

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
| 编排型（pipeline + LLM 两层） | screener（criteria/translate/screening/judge/report/service，2026-10-21 新增） |
服务通过 `core/container.py` DI 容器懒加载，路由经 `Depends(get_container)` 获取。

### Screener（智能选股，2026-10-21 v1；2026-10-22 v1.5 预设库）

两种选股模式（`POST /screener/runs` 的 `mode`）：

**freeform（v1）**：用户维护 `screener/criteria.md` 自然语言选股标准，手动触发：
① LLM 翻译标准为结构化规则（`ScreenerRule` 按 doc_hash 缓存，标准不变零 LLM 调用）
→ ② 确定性初筛（全市场快照 + 股票池过滤 + 量化规则求值 + 排名截断）
→ ③ LLM 逐只深判候选（单只失败隔离，结果落 `ScreenerJudgement` 供后续回测）
→ ④ Markdown 报告落 `screener/reports/`。

**presets（v1.5）**：预设标准库驱动，零 LLM 翻译。指标定义在 `screener/seeds.py`（24 个标准化指标，含 PE/PB/PS 派生估值与 TTM 现金流质量）+ 6 套内置预设（核心资产/高成长/深度价值/GARP/周期反转 + 金融行业专属「金融价值」，只读；用户可自建）。触发时传 `preset_ids` + `combine`（union/intersection/flatten），规则纯确定性组装（`compose.py`），报告标注每只候选命中的预设（`[预设名]` 前缀 + snapshot `hits`/`presets`）。前端 `/screener` 有模式切换 + PresetManager 抽屉。

估值与质量指标由 `screener/valuation.py` 即时派生：PE/PS 优先 TTM（上年年报 + 本期累计 − 上年同期；历史期缺失回退单期年化），PB = 市值 / (总资产−总负债)；盈利质量 = TTM 经营现金流/净利润、TTM 经营现金流/营收、应计比率。历史期可用 `scripts/backfill_financial_periods.py` 回补（如 2025Q1–Q4）。深判已接入知识库检索并对无证据命中做确定性降级；无定性标准时跳过 LLM。财务数据由 `core/financial_sync.py` 在工作日 3:15 定时刷新（`FINANCIAL_DATA_SCHEDULE`）。

股票池入口统一做风险卫生过滤：ST/*ST/退市、停牌/无行情、换手率低于 `SCREENER_MIN_TURNOVER`、总市值低于 `SCREENER_MIN_MARKET_CAP`；报告附「股票池卫生过滤」统计。

行业分类存 `market.stock_industry`（申万一级 31 个行业为主，新浪行业补缺；覆盖 5,663 只 A 股，主板 2,111/2,111）。选股候选携带 `industry`/`sector`，报告与深判上下文均展示行业。工业预设自动排除金融股（流动比率/毛利率/周转率口径不适用），`金融价值` 预设只筛选银行/非银金融。入库脚本：`scripts/ingest_industry_sw.py`（主）与 `scripts/ingest_industry_sina.py`（补缺）。

LLM 只在深判参与，筛选执行确定性。迁移 `b5d2f8a3c6e1` → `c8e1b7d4f2a9` → `b7c8d9e0f1a2` → `c1d2e3f4a5b6` → `d2e3f4a5b6c7` → `e3f4a5b6c7d8` → `f4a5b6c7d8e9`，schema `screener`。

### 预设回测（2026-10-23 MVP）

用历史数据验证预设的历史表现（`POST /screener/backtests`，body: `preset_id` + `years` 1-10；`GET /screener/backtests/{id}` 查结果）。

- **状态机**：`pending → running → completed/failed`（`screener.backtest_runs` 表），经持久任务 `screener_backtest` 后台执行，同时刻至多一个进行中（409）
- **数据**：日线走外部 MySQL 前复权库（`BACKTEST_MYSQL_URL`，仅存 .env），**逐只「边拉边灌」**——单票一次查询（~1200 行）立即落库 commit，本地行数即进度、≥200 根视为完整可断点续传、单票网络错误重试 3 次；同票同日重复行去重、(ticker,date) 唯一约束幂等；历史财务缺失报告期按需经 `ingest_marketwide_yjbb` 补拉（SAVEPOINT 单期隔离）；财务指标带 `announcement_date`，回测按公告日 <= 调仓日过滤（缺失公告日的历史行回退旧口径）；票池优先本地活跃公司，为空时取外部库区间 distinct symbol（含退市票，缓解幸存者偏差）
- **口径**（`screener/backtest.py` 纯函数）：调仓日 = 各披露截止日（Q1 4-30 / Q2 8-31 / Q3 10-31 / 年报次年 4-30）后首个交易日；**4 月调仓统一用上一年年报**，无未来函数；收益一律前复权 close；停牌（成交量为 0）按不可交易记 0 并标注；近似市值 = 调仓日收盘价 × 当前总股本；**已计佣金/卖出印花税/单边滑点**（`BACKTEST_COMMISSION_RATE` / `BACKTEST_STAMP_DUTY_RATE` / `BACKTEST_SLIPPAGE_RATE`）
- **产出**：result JSON `{summary: {total_return, cagr, max_drawdown, win_rate, ...}, yearly: [...]}` + Markdown 报告落 `screener/reports/`（含免责声明）
- 已知近似：外部库无历史股本 → 市值为近似值；财务可见性有公告日的按公告日过滤，缺失公告日的按披露截止日近似；涨跌停不可交易未单独建模。报告内均已声明。

### 定时筛选与变化日报（2026-10-24）

`core/screener_schedule.py` 在工作日 16:30（收盘后）按 `SCREENER_SCHEDULE_PRESETS`（默认 `core`）依次运行预设；已有进行中的 run 时跳过。每轮完成后与「相同 mode/combine/preset_ids（freeform 用 criteria_hash）」的上一轮 completed run 对比，只输出变化：新推荐/掉出推荐/新进候选/移出候选，Markdown 落到 `screener/reports/YYYY-MM-DD-diff-<run8>.md`，并写 `screener.diff` 事件。

API：`GET /api/v1/screener/runs/{run_id}/diff` 返回变化日报 Markdown 与 `has_previous`；前端历史运行表新增「日报」按钮。手动触发调度：`POST /api/v1/scheduler/run/screener_schedule`。

**数据采集（2026-10-22 东财风控后）**：全市场快照走新浪 `Market_Center` 分页接口；财务三表均为市场级一次调用——业绩报表 `stock_yjbb_em`（含 eps/营收同比/净利同比）、资产负债表 `stock_zcfz_em`、现金流量表 `stock_xjll_em`，全部经 `_AKSHARE_PROLOGUE` 反风控头（浏览器 UA + 直连 + IPv4 + urllib3 重试）。流动/速动比率、资产/存货/应收周转率、eps 与成长率另走东财 F10 主要指标 `RPT_F10_FINANCE_MAINFINADATA`（`LD`/`SD`/`TOAZZL`/`CHZZL`/`YSZKZZL`），分页 500/页、只保留 A 股前缀。`stock_zcfz_em` 原始表没有 `CURRENT_RATIO` 列，旧实现的 `CURRENT_RATIO÷100` 不会生效；单只报表接口仅作兜底保留。

### 数据分工原则（2026-10-14 定稿）

**接口管"数"，PDF 管"事"**：

- **定量层**：Market 中心是数字唯一事实源（akshare 直连入库 `market` schema）。报告/图表/比率引用财务数字只能走 Market 数据
- **定性层**：Document/Knowledge 管定性正文（MD&A/风险/附注/公告）。`document_chunks.content_type` 在解析时打标（`document/content_classifier.py` 纯函数），`/knowledge/search` 支持 `content_type=` 过滤
- **报告双轨**：Evidence 带 `content_nature`（quantitative/qualitative，LLM 批量分类）。数字论断走「已核实事实」/Market 区块禁止改写；定性论断内联 `[ev:id]`，前端可点击回跳证据卡
- **交叉验证**：`research/fact_validator.py` 把 structured_facts（财报抽取）与 Market 接口值比对，偏差 ≥10% → `Observation(attention)` 口径差异事件

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

## 数据库（8 个 Schema）

PostgreSQL 用 schema 做模块隔离，初始化 SQL 见 `docker/init.sql`：

| Schema | 表 |
|--------|-----|
| `company` | companies, company_tags |
| `market` | stock_prices, financial_metrics（含 announcement_date，PIT）, valuation_history（估值历史，PE/PB 分位源）, stock_industry（申万/新浪行业）, data_freshness |
| `document` | documents, document_chunks（含 content_type：mda/risk/notes/announcement/other） |
| `research` | research_sessions, research_evidences（含 content_nature：quantitative/qualitative）, research_reports |
| `portfolio` | holdings, investment_journal |
| `ai` | prompt_templates |
| `core` | event_log, task_records, observations |
| `screener` | screener_rules, screener_runs, screener_judgements, screener_metric_defs, screener_presets |

- `knowledge` / `dashboard` 无独立 schema：knowledge 复用 document 表 + Qdrant 向量，dashboard 跨 schema 聚合查询
- 行情/财务数据统一入库 PG（`market` schema），采集走 akshare 子进程直连（无外部 MySQL 依赖）

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
- 比率层端点：`GET /api/v1/market/ratios/{ticker}`（财务比率）、`GET /api/v1/market/ratios/{ticker}/valuation-percentile`（PE/PB 历史分位）
- 时间戳：数据库/API 统一使用 UTC（ISO 8601 带 `+00:00`）；前端展示转浏览器本地时区，报告内时间标注本地偏移

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
| | `OPENAI_BASE_URL` | https://api.openai.com/v1 | https://api.deepseek.com/v1 |
| | `OPENAI_MODEL` | gpt-4o | deepseek-chat |
| | `LLM_TIER_LIGHT_PROVIDER` / `LLM_TIER_LIGHT_MODEL` | ollama / qwen2.5:7b | openai / deepseek-chat |
| | `OLLAMA_MODEL` | llama3.1:70b | qwen3.5-98k:latest（注释） |
| Redis | `REDIS_URL` | redis://127.0.0.1:6380/0 | — |
| 文档 | `UPLOAD_DIR` / `MAX_UPLOAD_SIZE_MB` | data/uploads / 50 | — |
| | `CHUNK_SIZE` / `CHUNK_OVERLAP` | 512 / 64 | — |
| 市场 | `AKSHARE_ENABLED` / `YFINANCE_ENABLED` | true / true | — |
| 外部数据源 | `AKSHARE_MCP_DIR` / `NEWSNOW_MCP_SERVER_PATH` | /home/wsm/codes/akshare_mcp 等 | 机器相关 |
| 调度器 | `SCHEDULER_ENABLED` | **true** | — |
| | `FINANCIAL_DATA_SCHEDULE` | `15 3 * * 1-5` | — |
| | `SCREENER_SCHEDULE` | `30 16 * * 1-5` | — |
| | `SCREENER_SCHEDULE_PRESETS` | `core`（逗号分隔 style_tag） | — |
| 回测 | `BACKTEST_COMMISSION_RATE` | 0.0003（单边万三） | — |
| | `BACKTEST_STAMP_DUTY_RATE` | 0.0005（卖出） | — |
| | `BACKTEST_SLIPPAGE_RATE` | 0.001（单边千一） | — |
| 选股 | `SCREENER_MIN_TURNOVER` | 0.05（%） | — |
| | `SCREENER_MIN_MARKET_CAP` | 1e9（元） | — |
| 安全 | `SECRET_KEY` | 每次启动随机生成 | — |

> **默认是 Ollama，本机跑 DeepSeek**：代码里 `LLM_PROVIDER` 默认 `ollama`，本机 `.env` 设为 `openai` + DeepSeek（`deepseek-chat`，OpenAI 兼容端点 `https://api.deepseek.com/v1`）；light tier（证据分类/事实抽取）同样走云端。
> 完整变量清单见 `core/config.py`。

## AI 能力

| 功能 | 所需服务 |
|------|---------|
| 公司/行情浏览 | 无 |
| 文档索引 | Embedding 需 Ollama（`OLLAMA_EMBEDDING_MODEL`，本机 bge-m3） |
| 知识库搜索 | 无（纯向量 + BM25，无需 LLM） |
| 研究观点/问答/研究报告/证据分类 | DeepSeek / Ollama / OpenAI |

Ollama 版本过旧（<0.3.0）时 `/api/embed` 不可用，Embedding 降级为 BM25 稀疏检索 + RRF 融合，功能不受影响。

## 外部 MCP 数据源

- **akshare**：`market/akshare_executor.py` 调用外部 `akshare_mcp` venv（`AKSHARE_MCP_DIR`），子进程直连 Tencent/Sina/Eastmoney 数据源；价格/财务/估值三条采集链均无外部数据库依赖，可配云端 MCP 兜底（`AKSHARE_CLOUD_MCP_URL`，留空禁用）
- **newsnow**：`core/adapters/newsnow_mcp.py` 调用外部 newsnow MCP server（`NEWSNOW_MCP_SERVER_PATH` / `NEWSNOW_BASE_URL`）

## 后台任务

`core/task_manager.py`：PostgreSQL 持久化 `core.task_records` + worker 循环 + 自动重试 + `(type,key)` 去重 + 启动恢复。快速研究（`research/quick.py`）通过它后台跑 计划→搜集→报告 链，SSE 推流进度。

APScheduler 定时任务（`core/scheduler.py`）：`market_data_update`（工作日 2:00）、`financial_data_update`（工作日 3:15，全市场财务三表刷新，三类数据源 SAVEPOINT 隔离）、`screener_schedule`（工作日 16:30，定时选股 + 变化日报）、`observation_cycle`（工作日 5:30）、`event_log_cleanup`（周一 3:00）。状态见 `GET /api/v1/scheduler/status`。

## 测试

```bash
make test        # pytest，专用 airesearch_test 库 + 隔离 Qdrant 集合
```
当前全量 **391 passed / 2 failed / 2 skipped**；2 项失败为既有 research 证据继承用例（依赖本地小模型结构化输出，当前 Ollama 模型返回截断 JSON），与选股模块无关。screener + financial_sync 专项 **241 passed**。
