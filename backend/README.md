# AI Research OS — Backend

Python/FastAPI 后端。完整使用手册见根目录 [`USAGE.md`](../USAGE.md)。

## 技术栈

- **框架**: FastAPI + async SQLAlchemy + Pydantic v2
- **存储**: PostgreSQL（多 schema + pgvector）+ Qdrant（向量）+ Redis（缓存）
- **AI**: DeepSeek（OpenAI 兼容，本机默认）/ Ollama（本地 LLM + Embedding）
- **数据源**: akshare 子进程直连（A股/港股，Tencent/Sina/Eastmoney），yfinance（美股备选）
- **质量**: pytest ~330 用例 + ruff + mypy + pre-commit

## 架构

5 个业务模块 + Screener，依赖只向上：

```
Company → Market + Document → Knowledge(RAG) → Screener(确定性筛选)
```

> 2026-11-24 瘦身：research/portfolio/ai/dashboard 四模块代码已删除（数据库表保留）。2026-11-25 三次简化：LLM 深判整体退役（judge/judge_eval/eval 与 `core/llm_usage.py`、`core/system_routes.py` 均已删除），运行链路零 LLM（知识库问答除外）。

各模块文件结构并不完全统一：

| 形态 | 模块 |
|------|------|
| 完整四层 `models → schemas → service → routes` | company, document |
| `service/` + `routes/` 子目录拆分 | market（另含 domain/repositories/akshare_executor） |
| 薄模块（仅 routes + service，无自有 models/schemas） | knowledge（读写 document 表 + Qdrant） |
| 编排型（pipeline 两层，零 LLM） | screener（screening/fact_checks/report/service） |
服务通过 `core/container.py` DI 容器懒加载，路由经 `Depends(get_container)` 获取。

### Screener（智能选股，2026-10-21 v1；2026-10-22 v1.5 预设库；2026-11-25 深判退役）

预设是唯一运行入口（freeform 自由文本模式已删除，2026-11-25）。运行链路（`POST /screener/runs`，`mode` 固定 `presets`，零 LLM、单轮 ≤2 分钟）：
① 确定性初筛（全市场快照 + 股票池过滤 + 量化规则求值 + 行业隔离/相对排名 + 排名截断）
→ ② **事实检查确定性判定**（`screener/fact_checks.py`）：审计意见（KB 检索 + 关键词）、诉讼/处罚（KB 检索命中即 fail）、现金覆盖（财务指标计算）三检查器，任一 fail→reject、任一 not_found→insufficient
→ ③ 确定性判定落 `ScreenerJudgement`（量化命中 + fact_checks 结果；历史运行明细仍可查）
→ ④ Markdown 三段报告落 `screener/reports/`：量化筛选（数值+行业分位）→ 事实检查 → 不推荐/存疑原因（fact_checks not_found 项 + 缺数据项）。

**presets**：预设标准库驱动，零 LLM 翻译。指标定义在 `screener/seeds.py`（42 个标准化指标 + 8 套内置预设，只读）。**2026-11-25 起预设全部只读化**（含自建预设；规则改动走种子脚本重灌），触发时传 `preset_ids` + `combine`（union/intersection/flatten），规则纯确定性组装（`compose.py`），报告标注每只候选命中的预设（`[预设名]` 前缀 + snapshot `hits`/`presets`）。

估值与质量指标由 `screener/valuation.py` 即时派生：PE/PS 优先 TTM（上年年报 + 本期累计 − 上年同期；历史期缺失回退单期年化），PB = 市值 / (总资产−总负债)；盈利质量 = TTM 经营现金流/净利润、TTM 经营现金流/营收、应计比率；PEG = PE / 净利同比，FCF 收益率 = FCFF / 总市值。F10 主要指标另提供 ROIC、利息保障倍数、现金比率、FCFF、现金流/营业利润、实际税率、有息负债率。历史期可用 `scripts/backfill_financial_periods.py` 回补（如 2025Q1–Q4）。财务数据由 `core/financial_sync.py` 在工作日 3:15 定时刷新（`FINANCIAL_DATA_SCHEDULE`）。

股票池入口统一做风险卫生过滤：ST/*ST/退市、停牌/无行情、换手率低于 `SCREENER_MIN_TURNOVER`、总市值低于 `SCREENER_MIN_MARKET_CAP`；报告附「股票池卫生过滤」统计。

行业分类存 `market.stock_industry`（申万一级 31 个行业为主，新浪行业补缺；覆盖 5,663 只 A 股，主板 2,111/2,111）。选股候选携带 `industry`/`sector`，报告与深判上下文均展示行业。工业预设自动排除金融股（流动比率/毛利率/周转率口径不适用），`金融价值` 预设只筛选银行/非银金融。入库脚本：`scripts/ingest_industry_sw.py`（主）与 `scripts/ingest_industry_sina.py`（补缺）。

行业相对排名：候选在其行业内计算 ROE/ROIC/营收增长/净利增长/现金流质量/PE/PB 分位（金融行业用 PE/PB/ROE），综合为 `industry_score`；排序在筛选得分之后、市值之前使用；单行业候选上限 `SCREENER_MAX_PER_INDUSTRY`（默认 8）。报告展示行业分位。

近似命中已删除（2026-11-25 二次瘦身）。

行业专属指标（F10）：银行侧净息差、不良贷款/贷款总额、不良率、拨备率、一级资本充足率；保险侧净投资收益率、已赚保费、偿付能力充足率。SW 一级行业把保险与券商同归“非银金融”，服务层用 F10 保费/贷款字段进一步区分 `financial_type`，银行/保险预设据此只筛对应子行业。

筛选与判定全部确定性执行（2026-11-25 深判退役）。迁移 `b5d2f8a3c6e1` → `c8e1b7d4f2a9` → `b7c8d9e0f1a2` → `c1d2e3f4a5b6` → `d2e3f4a5b6c7` → `e3f4a5b6c7d8` → `f4a5b6c7d8e9` → `a5b6c7d8e9f0` → `b6c7d8e9f0a1` → `c7d8e9f0a1b2` → `d8e9f0a1b2c3` → `e9f0a1b2c3d4`，schema `screener`。

### 预设回测（脚本直调纯函数，落 JSON）

2026-11-25 回测去框架化：`backtest_service.py`（状态机+任务队列）、`backtest_report.py` 已删除，无 API/UI/任务；运行入口为脚本 `tools/run_backtest_queue.py`——直调 `screener/backtest.py` 纯函数 + `screener/backtest_data.py` 拉数，结果写 `screener/reports/backtest-{preset}-{date}.json`（summary/yearly/holdings 字段），不再创建 task/run 行。需 `BACKTEST_MYSQL_URL`。口径与数据层说明（调仓日/前复权/成本/分段稳健性）见 `screener/backtest.py` 与报告免责声明。

**首份有效成绩**（2026-10-25，3 年 / 9 个季度调仓期 / 基准 CSI300 CAGR +6.39%）：高成长 +23.84%（超额 +17.45%）、金融价值 +16.01%（超额 +9.61%、Sharpe 0.90）、周期反转 +2.65%、深度价值 -1.31%、核心资产 -8.37%、GARP -16.37%。全部 6 套均无空仓期。

### 定时筛选（2026-10-24；日报/Webhook 已删除）

`core/screener_schedule.py` 在工作日 16:30（收盘后）按 `SCREENER_SCHEDULE_PRESETS`（默认 `core`）依次运行预设；已有进行中的 run 时跳过。变化日报与失败告警 Webhook 已随三次简化删除（`screener/diff*.py`、`screener/notify.py`、`SCREENER_WEBHOOK_*` 配置项均移除）。

**调度状态与手动运行（2026-10-24）**：`GET /api/v1/screener/schedule` 返回 cron、定时预设、下次运行时间；`POST /api/v1/screener/schedule/run` 以持久任务 `screener_schedule` 后台执行一轮定时选股（不阻塞 HTTP，重复提交返回 409）。前端选股页「定时任务」卡片展示这些信息并提供「立即运行定时选股」。调度配置本身仍来自环境变量（`SCREENER_SCHEDULE` / `SCREENER_SCHEDULE_PRESETS`），UI 只读。

### 确定性结论（2026-11-25）

`ScreenerJudgement.verdict` 区分四种结论：`recommend` / `reject` / `insufficient` / `failed`（历史值保留兼容）。事实检查 fail→`reject`、not_found→`insufficient`；量化命中 + fact_checks 结果作为 reasons/criteria_hits 落库，前端明细弹窗仍逐只展示。

### 定性选股前置：知识库文档

事实检查器（审计意见/诉讼）依赖知识库检索。知识库为空时，检查判 `not_found` → 运行判「数据不足」（核心资产等纯量化预设不受影响）。报告概览会明确提示"知识库为空"。

使用步骤：文档中心上传年报/公告/研报 → 关联公司 → 等待后台索引完成（`is_indexed=true`）→ 再运行深度价值/GARP/周期反转/高成长/银行/保险等含事实检查的预设。

### 组合构建与推荐后表现（已删除，2026-11-25 二次瘦身）

组合构建/保存/再平衡（`screener/portfolio.py`/`rebalance.py`、`/portfolios` 端点）与推荐后表现/表现快照（`screener/performance.py`、`performance_snapshots`、`performance_snapshot` 定时任务）均已删除；数据库表与迁移历史保留。置信度校准的原始方法（按置信度分档对照实际收益）随表现接口一并移除。

### 数据质量前置检查（2026-10-24）

`GET /api/v1/screener/data-quality` 返回最新财务期与关键指标覆盖（ROE/营收/净利/经营现金流/总资产/ROIC/FCFF）、A 股公司行情覆盖（≥200 根日线）、最新行情日期、知识库文档/切片数，以及聚合告警（知识库为空、行情覆盖 <50%、财务库为空）。前端选股页「数据质量」卡片展示并高亮缺口；运行历史增加 全部/进行中/已完成/失败 筛选。

**加入自选（已删除，2026-11-25）**：`POST /runs/{run_id}/watchlist`（自选推送）与 `GET /runs/{id}/export`（CSV 导出）已随三次简化删除（前端无入口；自选状态直接在公司中心维护）。

**数据采集（2026-10-22 东财风控后）**：全市场快照走新浪 `Market_Center` 分页接口；财务三表均为市场级一次调用——业绩报表 `stock_yjbb_em`（含 eps/营收同比/净利同比）、资产负债表 `stock_zcfz_em`、现金流量表 `stock_xjll_em`，全部经 `_AKSHARE_PROLOGUE` 反风控头（浏览器 UA + 直连 + IPv4 + urllib3 重试）。流动/速动比率、资产/存货/应收周转率、eps 与成长率另走东财 F10 主要指标 `RPT_F10_FINANCE_MAINFINADATA`（`LD`/`SD`/`TOAZZL`/`CHZZL`/`YSZKZZL`），分页 500/页、只保留 A 股前缀。`stock_zcfz_em` 原始表没有 `CURRENT_RATIO` 列，旧实现的 `CURRENT_RATIO÷100` 不会生效；单只报表接口仅作兜底保留。

### 选股数据底座与预设评估（2026-10-25）

**数据规模**：行情 5,313 只 / 1,137 万行（主板 2,111 只全量，其中 2,099 只有 ≥200 根日线，其余 12 只为新股）；财务 15 个报告期 × 32 指标（PIT 用法定披露截止日，不用东财滚动「最新公告日期」）；知识库 103 份年报 / 55,135 切片。

**5 年回测（15 个报告期，基准 −4.56%）**

| 预设 | 累计收益 | 超额 | 备注 |
|------|---------|------|------|
| 金融价值 | +6.89% | +11.45% | 3 年窗口同样跑赢（+14.56% 超额），跨窗口稳定 |
| 深度价值 | +5.60% | +10.16% | 靠纯量化，定性增量未验证 |
| 周期反转 | −0.87% | +3.69% | 与基准持平 |
| 高成长 | −6.90% | −2.34% | 最大回撤 −59.94%，3 年窗口 +23.59%，对窗口极敏感 |
| 核心资产 | −14.92% | −10.36% | 阈值敏感性扫描证明调参无效 |
| GARP | −23.61% | −19.05% | 同上 |

> 阈值敏感性结论（`tools/rule_sensitivity.py`，5 年窗口）：`roic` 规则对结果无影响（非瓶颈）；放宽 `roe` 是唯一有效变量但救不活核心资产/GARP；放宽 `net_margin` 反而更差。**质量因子类预设应重构而非继续调阈值。**

**实时判定（2026-11-25 深判退役前留存，仅作历史参考）**

| 预设 | 候选 | 推荐 | 拒绝 | 数据不足 | 可用性 |
|------|------|------|------|----------|--------|
| 高成长 | 46 | 15 | 0 | 31 | 可作候选池，需人工剔除软证据 |
| 深度价值 | 50 | 0 | 10 | 40 | 不可用（见下） |
| 金融价值 | 10 | 2（杭州银行 0.95、青岛银行 0.92） | 0 | 8 | 可直接参考 |

**判定链路（现口径）**：`screen` → 事实检查确定性判定（`fact_checks.py`：审计意见文本匹配 + 诉讼 KB 检索 + 现金覆盖财务计算）→ 确定性结论落 `ScreenerJudgement`。深判逐条检索与证据守卫已随退役删除；「事实性/合规性标准不应交给 LLM 判」的历史教训是本轮深判整体退役的直接动因。

**预设定性标准可验证性改造**：原标准（「细分行业排名前二」「行业渗透率持续提升」）年报几乎不会如此表述。已把 5 套预设的定性标准改写为「年报真实存在的章节/字段」，负向标准先锚定可引用正向证据（审计意见/监管指标）再谈未披露。备份 `data/presets_qualitative_backup.json`，脚本 `tools/rewrite_presets_qualitative.py`（已归档 `tools/archive/`）。

**置信度语义（历史）**：`confidence` 原为 LLM 自评（0–1），**未校准、非概率**。深判退役后仅历史运行数据中保留该字段，用于历史明细排序展示；新运行由确定性判定生成，无 LLM 置信度。

### 数据分工原则（2026-10-14 定稿）

**接口管"数"，PDF 管"事"**：

- **定量层**：Market 中心是数字唯一事实源（akshare 直连入库 `market` schema）。报告/图表/比率引用财务数字只能走 Market 数据
- **定性层**：Document/Knowledge 管定性正文（MD&A/风险/附注/公告）。`document_chunks.content_type` 在解析时打标（`document/content_classifier.py` 纯函数），`/knowledge/search` 支持 `content_type=` 过滤

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
| `research` / `portfolio` / `ai` | **代码已删除（2026-11-24），表保留未清理** |
| `core` | event_log, task_records（observations 表为已删观测引擎残留） |
| `screener` | screener_rules*（代码已删，表保留）, screener_runs, screener_judgements, screener_metric_defs, screener_presets, screener_portfolios*（代码已删，表保留）, performance_snapshots*（同上） |

- `knowledge` 无独立 schema：复用 document 表 + Qdrant 向量
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
导入示例公司与默认数据（研究相关 seeding 已随模块删除）。

## API 约定

- 所有端点前缀 `/api/v1`，交互式文档见 http://localhost:8000/docs
- 异常统一走 `core/exceptions.py` → `api/app.py` 集中 handler，返回结构化 JSON：404 / 422 / 409 / 401 / 403 / 502 / 500
- 接口速查：直接看各模块 `routes.py`，或根目录 `USAGE.md`「功能模块详解」
- Screener 报告指针：`GET /api/v1/screener/latest-report` 返回最近一次 completed 运行的报告路径/内容（无报告时 404，前端优雅降级）
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
| | `OLLAMA_MODEL` | llama3.1:70b | qwen3.5-98k:latest（注释） |
| | `OLLAMA_NUM_CTX` | 8192 | —（仅知识库问答等长上下文场景；仅 Ollama provider 生效） |
| Redis | `REDIS_URL` | redis://127.0.0.1:6380/0 | — |
| 文档 | `UPLOAD_DIR` / `MAX_UPLOAD_SIZE_MB` | data/uploads / 50 | — |
| | `CHUNK_SIZE` / `CHUNK_OVERLAP` | 512 / 64 | — |
| 市场 | `AKSHARE_ENABLED` / `YFINANCE_ENABLED` | true / true | — |
| 外部数据源 | `AKSHARE_MCP_DIR` | /home/wsm/codes/akshare_mcp 等 | 机器相关 |
| 调度器 | `SCHEDULER_ENABLED` | **true** | — |
| | `FINANCIAL_DATA_SCHEDULE` | `15 3 * * 1-5` | — |
| | `SCREENER_SCHEDULE` | `30 16 * * 1-5` | — |
| | `SCREENER_SCHEDULE_PRESETS` | `core`（逗号分隔 style_tag） | — |
| 回测 | `BACKTEST_COMMISSION_RATE` | 0.0003（单边万三） | — |
| | `BACKTEST_STAMP_DUTY_RATE` | 0.0005（卖出） | — |
| | `BACKTEST_SLIPPAGE_RATE` | 0.001（单边千一） | — |
| | `BACKTEST_RISK_FREE_RATE` | 0.02（年化） | — |
| 选股 | `SCREENER_MIN_TURNOVER` | 0.05（%） | — |
| | `SCREENER_MIN_MARKET_CAP` | 1e9（元） | — |
| | `SCREENER_MAX_PER_INDUSTRY` | 8（单行业候选上限） | — |
| 安全 | `SECRET_KEY` | 每次启动随机生成 | — |

> **默认是 Ollama，本机跑 DeepSeek**：代码里 `LLM_PROVIDER` 默认 `ollama`，本机 `.env` 设为 `openai` + DeepSeek（`deepseek-chat`，OpenAI 兼容端点 `https://api.deepseek.com/v1`）；light tier（证据分类/事实抽取）同样走云端。
> 完整变量清单见 `core/config.py`。

## AI 能力

| 功能 | 所需服务 |
|------|---------|
| 公司/行情浏览 | 无 |
| 文档索引 | Embedding 需 Ollama（`OLLAMA_EMBEDDING_MODEL`，本机 bge-m3） |
| 知识库搜索 | 无（纯向量 + BM25，无需 LLM） |
| 知识库问答 | DeepSeek / Ollama / OpenAI |
| Screener 运行链路 | 无（2026-11-25 深判退役，全程确定性） |

Ollama 版本过旧（<0.3.0）时 `/api/embed` 不可用，Embedding 降级为 BM25 稀疏检索 + RRF 融合，功能不受影响。

## 批量导入年报（巨潮资讯网）

定性选股与文档问答依赖知识库。批量补年报分两步（均幂等，可重复运行）：

```powershell
cd backend
# 1) 下载：默认取最近一次选股运行的全部候选股票（或传 run_id）
.venv\Scripts\python tools\fetch_cninfo_reports.py
# 2) 上传+索引：自动关联 company_id，轮询到 is_indexed=true
.venv\Scripts\python tools\upload_reports.py
```

脚本会从巨潮公告接口取最新一期主年报（排除摘要/英文/更正），存到 `data/uploads/kb/` 并写 `manifest.csv`；上传时缺失公司会自动补进 `company.companies`。详见 [`tools/README.md`](tools/README.md#批量获取年报巨潮资讯网)。

## 外部 MCP 数据源

- **akshare**：`market/akshare_executor.py` 调用外部 `akshare_mcp` venv（`AKSHARE_MCP_DIR`），子进程直连 Tencent/Sina/Eastmoney 数据源；价格/财务/估值三条采集链均无外部数据库依赖，可配云端 MCP 兜底（`AKSHARE_CLOUD_MCP_URL`，留空禁用）

## 后台任务

`core/task_manager.py`：PostgreSQL 持久化 `core.task_records` + worker 循环 + 自动重试 + `(type,key)` 去重 + 启动恢复。

APScheduler 定时任务（`core/scheduler.py`）：`market_data_update`（工作日 2:00）、`financial_data_update`（工作日 3:15，全市场财务三表刷新，三类数据源 SAVEPOINT 隔离）、`screener_schedule`（工作日 16:30，定时选股）、`event_log_cleanup`（周一 3:00）。状态见 `GET /api/v1/scheduler/status`。（`performance_snapshot` 任务已随表现跟踪删除；变化日报与失败告警 Webhook 已随三次简化删除，2026-11-25。）

## 测试

```bash
make test        # pytest，专用 airesearch_test 库 + 隔离 Qdrant 集合
```
2026-11-24 一次瘦身删除 research/portfolio/ai 用例；2026-11-25 二次瘦身删除组合/表现/取消/近似命中/freeform 用例（新增 `test_fact_checks.py`）；三次简化删除 judge/judge_eval/diff/notify/backtest service/actions 用例（当前 ~330 用例水平）。既有失败豁免：`test_announcement_date_filters_future_data`、`test_presets_union_with_financials`（日期依赖）、`test_snippet_hit_with_citation_kept`（'SnippetKnowledge' 无 session 属性）、`test_skips_when_metric_present` 及 document/knowledge 4 个 Ollama 环境失败。
