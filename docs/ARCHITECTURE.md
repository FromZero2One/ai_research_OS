# AI Research OS 架构文档

> 更新日期：2026-11-24（项目瘦身裁剪后）。裁剪决策见 `docs/superpowers/specs/2026-11-24-slim-to-value-screener-design.md`。

## 1. 系统定位

个人 AI 价值投资筛选器（单用户本地工具）。核心链路：

```
数据采集 → 价值筛选 → LLM 深判 → 回测验证 → 定时推送
```

设计信条：**数据与规则管筛选，AI 只做有据可查的深判**。筛选执行是确定性的（相同输入必然相同输出）；LLM 仅参与逐只深判，且其结论必须引用年报证据（`[n]` 引用守卫），否则降级为「数据不足」。

## 2. 总体架构

```text
                User
                 │
          Screener Workspace
          (Vue 3 SPA, :5173)
                 │
                 ▼
          API Gateway (FastAPI, :8000)
                 │
  ┌───────────────────────────────────────────┐
  │             Application Layer             │
  ├───────────────────────────────────────────┤
  │  Company  │  Market   │  Document         │
  │  (股票池) │ (数字源)  │ (年报PDF→切片)      │
  │           │           ├───────────────────┤
  │           │           │  Knowledge (RAG)  │
  │           │           │  深判证据检索      │
  │           │           ├───────────────────┤
  │           │           │  Screener         │
  │           │           │  筛选/深判/回测/推送│
  └───────────────────────────────────────────┘
                 │
  ┌───────────────────────────────────────────┐
  │               Core Layer                  │
  ├───────────────────────────────────────────┤
  │ DB │ Vector │ LLM │ Cache │ Scheduler     │
  │    (Qdrant)│       │(Redis)│ (APScheduler)│
  └───────────────────────────────────────────┘
```

### 2.1 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic |
| 前端 | Vue 3.5 + Vite + TypeScript + Element Plus + TanStack Vue Query + ECharts |
| 存储 | PostgreSQL 16（pgvector，多 schema）+ Qdrant（向量）+ Redis :6380（缓存） |
| 数据源 | akshare 子进程直连（A股/港股：Tencent/Sina/Eastmoney）；yfinance（美股备选）；回测可选外部 MySQL 前复权日线 |
| AI | DeepSeek（OpenAI 兼容，默认）/ Ollama / 任意 OpenAI 兼容 API；嵌入 BGE-M3（Ollama） |

### 2.2 依赖规则

**只允许向上依赖**（下层不知道上层）：

```
company → market / document → knowledge → screener
                      ↑
                 core（地基，无业务语义）
```

- `core/` 不 import 任何业务模块
- `knowledge` 无自有 DB schema，读写 `document` 表 + Qdrant
- 路由经 DI（`core/container.py` 懒加载单例，`Depends(get_container)`）取服务

## 3. 模块清单（backend/）

| 模块 | 职责 | 关键文件 |
|---|---|---|
| `company` | 公司档案、标签、Thesis（手动）、自选 `is_active` | models / service / routes |
| `market` | 行情、财务三表、比率层、估值分位、行业分类——**数字唯一事实源** | `service/` + `routes/` 子目录 + domain/repositories/akshare_executor |
| `document` | 年报 PDF 上传→解析（表格按词坐标重建 Markdown）→切片打标（mda/risk/notes/announcement）→嵌入→索引 | content_classifier / table_extractor |
| `knowledge` | 混合 RAG（Qdrant 稠密 + BM25 稀疏 + RRF + Reranker）、文档问答——**深判的证据来源** | service / routes |
| `screener` | 价值筛选全链：量化初筛、LLM 深判、回测、组合、日报推送（见 §4） | 33 个文件的编排型模块 |
| `core` | 配置、DB、调度、任务队列、事件日志、观测引擎、LLM 适配、用量统计 | 见下 |

### 3.1 core/ 基础设施

| 文件 | 职责 |
|---|---|
| `config.py` | pydantic-settings，读 `backend/.env`（大小写不敏感） |
| `database.py` | 异步引擎 + `get_db` / `managed_session` |
| `container.py` | DI 容器（懒加载单例） |
| `scheduler.py` | APScheduler：market_data_update（工作日2:00）、financial_data_update（3:15）、screener_schedule（16:30）、performance_snapshot（17:10）、observation_cycle（5:30）、event_log_cleanup（周一3:00） |
| `task_manager.py` | PG 持久任务队列 + worker + 重试 + `(type,key)` 去重 + 启动恢复 |
| `event_log.py` / `event_service.py` | `core.event_log` 只写审计日志（never update/delete） |
| `observation.py` / `observation_engine.py` | 自选股观测（价格异动/行业异动；research 时效逻辑已随瘦身移除） |
| `financial_sync.py` / `market_sync.py` | 定时数据采集（三类数据源 SAVEPOINT 隔离） |
| `screener_schedule.py` / `performance_schedule.py` | 定时选股 + 变化日报；表现快照 |
| `adapters/` | llm（DeepSeek/Ollama 分级）、embedding（BGE-M3）、reranker、vector_store、cache、pdf_parser、newsnow_mcp |
| `system_routes.py` | `GET /api/v1/ai/usage`（AI 模块删除后保留的用量端点） |
| `proxy_cleanup.py` | 启动前剥离代理环境变量（否则 httpx 打不通本地服务） |

> 2026-11-24 瘦身删除：`research/`、`portfolio/`、`ai/`、`dashboard/` 模块代码（数据库表与迁移历史保留，回捡 `git revert`）。

## 4. Screener 模块（核心）

### 4.1 筛选流水线

```
POST /api/v1/screener/runs
  │
  ├─① 标准解析      freeform: LLM 翻译 criteria.md → 规则（doc_hash 缓存，标准不变零 LLM）
  │                 presets : 纯确定性组装（compose.py），零 LLM
  ├─② 股票池卫生    ST/*ST/退市/停牌/低换手(<SCREENER_MIN_TURNOVER)/小市值(<SCREENER_MIN_MARKET_CAP)
  ├─③ 量化初筛      42 指标（估值/现金流质量/因子深度/银行保险专属）× 8 内置预设
  │                 行业隔离（工业预设排金融股；金融预设只看银行/保险）
  │                 行业相对排名 + 单行业上限（SCREENER_MAX_PER_INDUSTRY）
  ├─④ LLM 逐条深判  每条定性标准独立检索知识库（_retrieve_per_criterion）
  │                 → 证据守卫（hit 必须带 [n] 引用，否则降级 insufficient）
  │                 → 三态结论：recommend / reject / insufficient（+failed）
  ├─⑤ 报告          Markdown 落 screener/reports/（含数据时效标注、近似命中、缺数据排除表）
  └─⑥ 产出          ScreenerJudgement 落库 → CSV 导出 / 组合构建 / 变化日报 / Webhook
```

### 4.2 回测

- 调仓日 = 法定披露截止日后首个交易日，4 月统一用上一年年报（**无未来函数**）
- 数据：外部 MySQL 前复权日线逐只「边拉边灌」（断点续传）+ akshare 历史财务按需补拉
- 已计交易成本：佣金 / 印花税 / 滑点（`BACKTEST_*_RATE`）
- 风险指标：Sharpe / Sortino / Calmar / 最大回撤 / 沪深300 超额 / 对半分段稳健性

### 4.3 自动化闭环

- 工作日 16:30 定时筛选 → 与同口径上一轮（规则哈希比对）对比 → 变化日报（新推荐/掉出/新进/移出）
- `SCREENER_WEBHOOK_URL` 推送企微/飞书/钉钉；运行失败同样告警
- 表现快照（工作日 17:10）：推荐股 T+1 买入的 1/3/6/12 月收益 vs 沪深300 超额

### 4.4 关键设计约束

1. **确定性筛选**：预设模式下相同输入必然相同输出（规则缓存 + 纯函数组装）
2. **LLM 只判叙事**：事实性/合规性标准（审计意见、诉讼、现金覆盖）应下沉为确定性判定——LLM 判不了且不该判
3. **confidence 未校准**：仅为 LLM 自评（实测聚集 0.95/0.92/0.85 三档），只用于排序与组合权重，禁止当胜率/概率

## 5. 数据架构

### 5.1 PostgreSQL Schema（一模块一 schema）

| Schema | 表 | 状态 |
|---|---|---|
| `company` | companies, company_tags | 活跃 |
| `market` | stock_prices, financial_metrics（PIT 公告日）, valuation_history, stock_industry, data_freshness | 活跃 |
| `document` | documents, document_chunks（content_type 打标） | 活跃 |
| `core` | event_log（只写）, task_records, observations | 活跃 |
| `screener` | screener_rules, screener_runs, screener_judgements, screener_metric_defs, screener_presets, screener_portfolios, performance_snapshots | 活跃 |
| `research` / `portfolio` / `ai` | 旧表 | **代码已删，表保留**（无 drop 迁移） |

迁移：Alembic 线性链 ~30 版本；向量不进 PG（用 Qdrant 独立 collection）。

### 5.2 数据分工原则（接口管"数"，PDF 管"事"）

- **定量层**：Market 中心是数字唯一事实源——报告/比率/图表引用财务数字只能走 `market` schema，禁止从 PDF 抠数
- **定性层**：Document/Knowledge 管定性正文（MD&A/风险/附注/公告），切片带 content_type 可定向检索
- 深判上下文中数字区块标注「禁止改写」

### 5.3 数据采集链

- 全市场快照：新浪 `Market_Center` 分页（东财风控应对）
- 财务三表：业绩报表 `stock_yjbb_em` / 资产负债 `stock_zcfz_em` / 现金流 `stock_xjll_em`（市场级一次调用，~5000 只/期）
- 比率补充：东财 F10 主要指标 `RPT_F10_FINANCE_MAINFINADATA`（流动/速动/周转/成长率、ROIC/FCFF 等）
- 行业：申万一级为主（`ingest_industry_sw.py`），新浪补缺
- 年报：巨潮资讯 `tools/fetch_cninfo_reports.py` → `tools/upload_reports.py`（幂等）

## 6. 前端架构（frontend/）

```
src/
├── router/            # 7 条路由；/ 重定向 /screener
├── views/             # 6 页面：Screener(首页)/Companies/CompanyDetail/Market/Documents/Knowledge/System
├── components/        # StockSearch / StockChart / CommandPalette / Sidebar / PresetManager
├── stores/api.ts      # 唯一数据层：fetch + TanStack Query 泛型 hooks（视图不直接 fetch）
└── styles/
```

- 数据访问铁律：所有 API 调用集中 `stores/api.ts`；缓存失效/422 格式化统一处理
- `npm run build`（vue-tsc -b）为类型检查门槛；OpenAPI 类型生成（`npm run gen`）为按需工具

## 7. 横切关注点

| 关注点 | 方案 |
|---|---|
| 认证 | **无（by design）**——单用户本地工具；`core/security.py` 存在但有意不接；CORS 仅 localhost:5173 |
| 异常 | `core/exceptions.py` 统一 handler → 结构化 JSON（404/422/409/502/...） |
| 时间 | 全链 UTC ISO-8601；前端展示转本地时区 |
| 审计 | `core.event_log` 只写审计（Thesis 变更/文档上传/筛选事件等） |
| 任务 | HTTP 触发的长活（筛选/回测）走持久任务队列；失败自动重试 + 启动恢复；运行可协作式取消 |
| 可观测 | structlog；`/scheduler/status`；数据覆盖矩阵 `GET /market/freshness/coverage`；LLM 用量 `/ai/usage` |
| 测试 | pytest（conftest 自动建 `airesearch_test` 库，拒绝连开发库）；ruff/mypy 仅对改动文件（全仓历史债务不碰） |

## 8. 已裁剪模块（2026-11-24）

| 模块 | 原职责 | 裁剪原因 |
|---|---|---|
| `research` | 研究会话/证据/报告/Thesis 工作流 | 与 Screener 深判报告职责重叠 |
| `portfolio` | 持仓/投资日记（后端） | 无前端闭环，维护成本>价值 |
| `ai` | Prompt 模板 CRUD/执行 | AI 能力已内嵌知识问答与深判 |
| `dashboard` | 跨模块聚合仪表盘 | 首页即 Screener，聚合无必要 |

保留物：数据库表、Alembic 历史、`/ai/usage` 端点（迁至 `core/system_routes.py`）、手动 Thesis。回捡方式：`git revert` 裁剪提交。

## 9. 已知架构级缺口

1. 事实性定性标准（审计意见等）仍走 LLM，应下沉为文本匹配 + 指标确定性判定
2. 置信度未校准，不能当概率使用
3. 回测市值用「当前总股本 × 历史价」近似，频繁再融资公司有偏差；退市股处理未确认
4. 数据源单点：财务/新闻依赖东财
5. `valuation_history` 空（上游无数据），估值历史分位未接入选股
