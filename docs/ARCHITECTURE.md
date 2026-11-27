# AI Research OS 架构文档

> 更新日期：2026-11-26（六次简化完成后）。历史决策：二次瘦身 `2026-11-24-slim-to-value-recommendation-design.md`、三次简化 `2026-11-25-llm-retire-simplify-design.md`、六次简化 `2026-11-26-deadweight-clear-analysis-quality-design.md`。

## 1. 系统定位

个人价值投资清单生成器（单用户本地工具）。核心链路：

```
数据采集 → 8 套策略量化筛选 → 事实检查确定性判定 → Markdown 价值推荐清单（每日自动）
```

设计信条：**数据与规则管筛选与判定，全系统零 LLM**（仅知识检索的 embedding 用 Ollama）。筛选与判定全程确定性（相同输入必然相同输出）；运行链路零 LLM 依赖，单轮 ≤2 分钟（冒烟实测 88 秒）。

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
  │  (只读列表)│ (数字源)  │ (年报PDF→切片)      │
  │           │           ├───────────────────┤
  │           │           │  Knowledge (RAG)  │
  │           │           │  混合检索（零问答）  │
  │           │           ├───────────────────┤
  │           │           │  Screener         │
  │           │           │  筛选/事实检查/报告 │
  └───────────────────────────────────────────┘
                  │
  ┌───────────────────────────────────────────┐
  │               Core Layer                  │
  ├───────────────────────────────────────────┤
  │ DB │ Vector │ Embedding │ Scheduler       │
  │    (Qdrant)│ (Ollama)   │ (APScheduler)   │
  └───────────────────────────────────────────┘
```

### 2.1 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.13 + FastAPI + SQLAlchemy 2.0 (async) + Pydantic v2 + Alembic |
| 前端 | Vue 3.5 + Vite + TypeScript + Element Plus + TanStack Vue Query + ECharts |
| 存储 | PostgreSQL 16（多 schema）+ Qdrant（向量）+ Redis :6380（缓存） |
| 数据源 | akshare 子进程直连（A股：Tencent/Sina/Eastmoney）；回测可选外部 MySQL 前复权日线 |
| AI | **无 LLM（已全部退役）**；嵌入 BGE-M3（Ollama） |

### 2.2 依赖规则

**只允许向上依赖**（下层不知道上层）：

```
company → market / document → knowledge → screener
                      ↑
                 core（地基，无业务语义）
```

- `core/` 不 import 任何业务模块
- `knowledge` 无自有 DB schema，读写 `document` 表 + Qdrant
- 路由经 DI（`core/container.py`，`Depends(get_container)`）取服务

## 3. 模块清单（backend/）

| 模块 | 职责 | 关键文件 |
|---|---|---|
| `company` | **只读列表**（`GET /companies`，供文档关联下拉）；Company 表保留供 screener 数据质量统计、market search、document 外键读 | models / service / routes |
| `market` | 行情、财务三表、比率层、估值分位、行业分类——**数字唯一事实源** | `service/` + `routes/` 子目录 + akshare_executor |
| `document` | 年报 PDF 上传→解析（表格按词坐标重建 Markdown）→切片打标（mda/risk/notes/announcement）→嵌入→索引 | content_classifier / table_extractor |
| `knowledge` | 混合 RAG（Qdrant 稠密 + BM25 稀疏 + RRF + Reranker）、检索服务（问答已退役） | service / routes |
| `screener` | 价值筛选全链：量化初筛、事实检查、三段报告（见 §4，18 个文件） | compose / screening / fact_checks / report |
| `core` | 配置、DB、调度、事件审计、embedding 适配 | 见下 |

### 3.1 core/ 基础设施

| 文件 | 职责 |
|---|---|
| `config.py` | pydantic-settings，读 `backend/.env`（已无任何 LLM 变量） |
| `database.py` | 异步引擎 + `get_db` / `managed_session` |
| `container.py` | DI 容器（懒加载单例） |
| `scheduler.py` | APScheduler：market_data_update（工作日 18:00）、financial_data_update（3:15）、screener_schedule（16:30）——仅此三个 job |
| `background.py` | 进程内后台协程 `spawn_bg`（fire-and-forget，强引用防 GC）——选股触发/文档索引的统一后台执行路径 |
| `event_log.py` | `core.event_log` 只写审计（never update/delete），记录 screener.triggered/completed/failed |
| `event_service.py` | EventLogger 写入（查询/清理 API 已随七次简化删除） |
| `financial_sync.py` / `market_sync.py` | 定时数据采集（SAVEPOINT 隔离） |
| `screener_schedule.py` | 定时选股（默认跑 financial,value；失败仅 logger.error，无推送） |
| `adapters/` | embedding（BGE-M3）、reranker、vector_store、cache、pdf_parser |
| `proxy_cleanup.py` | 启动前剥离代理环境变量（否则 httpx 打不通本地服务） |

## 4. Screener 模块（核心）

### 4.1 筛选流水线（零 LLM）

```
POST /api/v1/screener/runs（mode 必须为 presets）
  │
  ├─① 规则组装     compose.py：8 套只读内置预设 → quant_rules / qualitative / fact_checks 三通道（纯函数，零 LLM）
  ├─② 股票池卫生   ST/*ST/退市/停牌/低换手/小市值过滤（pool.py）
  ├─③ 量化初筛     52 指标（估值 TTM/现金流质量/因子深度/银行保险专属）× 命中预设评估
  │               行业隔离（工业预设排金融股；金融预设只看对应子行业）
  │               行业相对排名 + 单行业上限（SCREENER_MAX_PER_INDUSTRY）
  ├─④ 事实检查     fact_checks.py 三检查器（确定性）：
  │               audit_opinion（KB 检索+关键词）/ litigation（命中即 fail）/ cash_coverage（财务计算）
  │               cash_coverage 支持 exempt_financial_type 豁免——券商/金融股口径不适用返回
  │               exempt（视同通过），不再集体 insufficient
  │               verdict：任一 fail→reject；任一 not_found→insufficient；exempt/pass→recommend
  ├─⑤ 判定落库     _auto_pass_judgement 确定性生成 ScreenerJudgement（confidence 已退役不写，逐只幂等落库）
  └─⑥ 三段报告     Markdown 落 screener/reports/：量化筛选（数值+行业分位）→ 事实检查（exempt 显示
                  「不适用（已豁免）」）→ 不推荐/存疑原因；尾部「较上一轮」对比（同口径上一轮 completed
                  run 的推荐集：新增/移出/连续推荐）；预设标注回测证据 grade 徽标
                  GET /screener/latest-report 单指针直载
```

### 4.2 回测（脚本化，非链路）

- `tools/run_backtest_queue.py` 直调 `backtest.py` 纯函数，结果落 `screener/reports/backtest-{preset}-{date}.json`
- 调仓日 = 法定披露截止日后首个交易日（无未来函数）；已计佣金/印花税/滑点
- PIT 财务加载 `_load_financials_by_period` 在 `backtest_data.py`（含公告日钳制）
- 需 `BACKTEST_MYSQL_URL`（外部前复权日线）
- ScreenerBacktestRun ORM 类已删（`screener.backtest_runs` 表保留）

### 4.3 定时任务

- 工作日 16:30 自动按 `SCREENER_SCHEDULE_PRESETS`（默认 `financial,value`——回测验证过的两套）筛选 → 报告落盘 → `latest-report` 指针更新
- 失败仅 `logger.error`（Webhook 推送已删）；`GET /screener/schedule` 可查状态、`POST /schedule/run` 手动触发

### 4.4 关键设计约束

1. **确定性筛选与判定**：相同输入必然相同输出；全系统零 LLM
2. **预设只读**：内置 8 套预设经 seeds.py 定义（各带 `evidence {grade, note}` 静态元数据，不入库）+ `scripts/reseed_builtin_presets.py` 幂等重灌，无 CRUD（防回测口径漂移）
3. **表保留模式**：删除功能只删 ORM 类/代码，DB 表永不 drop（portfolios/performance_snapshots/backtest_runs/screener_rules 等均为此状态）
4. **证据分层**：预设按 5 年回测标注 verified/neutral/failed（`PRESET_EVIDENCE`），报告显式标注，失效预设默认不进定时任务

## 5. 数据架构

### 5.1 PostgreSQL Schema（一模块一 schema）

| Schema | 表 | 状态 |
|---|---|---|
| `company` | companies（company_tags 表保留，ORM 已删） | 活跃（写入口已删，仅读；写入仅剩 seed_data.py） |
| `market` | stock_prices, financial_metrics（PIT 公告日）, valuation_history（无喂数入口，表保留）, stock_industry, data_freshness | 活跃 |
| `document` | documents, document_chunks（content_type 打标） | 活跃 |
| `core` | event_log（只写审计；task_records 表为退役队列残留） | 部分活跃 |
| `screener` | screener_runs, screener_judgements（confidence 列保留恒空）, screener_metric_defs, screener_presets 活跃；screener_rules, screener_portfolios, performance_snapshots, backtest_runs **表保留代码已删** | 部分活跃 |
| `research` / `portfolio` / `ai` | 旧表 | **代码已删，表保留** |

迁移：Alembic 线性链 ~30 版本；向量不进 PG（Qdrant 独立 collection）。

### 5.2 数据分工原则（接口管"数"，PDF 管"事"）

- **定量层**：Market 中心是数字唯一事实源——禁止从 PDF 抠数
- **定性层**：Document/Knowledge 管定性正文，切片带 content_type 可定向检索（fact_checks 的审计意见/诉讼检查走轻量检索：top_k=3、单次/检查）

### 5.3 数据采集链

- 全市场快照：新浪 `Market_Center` 分页（东财风控应对）
- 财务三表：业绩/资产负债/现金流（市场级一次调用，~5000 只/期）
- F10 主要指标：ROIC/FCFF/流动速动/周转/成长率
- 行业：申万一级为主，新浪补缺
- 年报：巨潮资讯批量拉取 → 上传索引（幂等；现有 103 份 / 55,135 切片）

## 6. 前端架构（frontend/）

```
src/
├── router/            # 4 条路由；/ 重定向 /screener
├── views/             # 4 页面：Screener(首页)/Market/Documents/System
├── components/        # StockSearch / StockChart / FinancialBars / CommandPalette / Sidebar
├── stores/api.ts      # 唯一数据层：fetch + TanStack Query 泛型 hooks（视图不直接 fetch）
└── styles/
```

- 数据访问铁律：所有 API 调用集中 `stores/api.ts`
- `npm run build`（vue-tsc -b）为类型检查门槛
- Screener.vue 为价值推荐清单视图：触发条（预设多选+池+组合方式）→ 数据质量卡 → 运行状态 → 报告主体（latest-report 直载 + 历史列表；判定明细无置信度列）

## 7. 横切关注点

| 关注点 | 方案 |
|---|---|
| 认证 | **无（by design）**——单用户本地工具；CORS 仅 localhost:5173 |
| 异常 | `core/exceptions.py` 统一 handler → 结构化 JSON |
| 时间 | 全链 UTC ISO-8601 |
| 审计 | `core.event_log` 只写（screener 触发/完成/失败等） |
| 任务 | HTTP 触发的筛选/文档索引经 `core/background.py` 协程直跑（task_manager 持久队列已退役）；幂等靠 screener_runs 唯一索引 |
| 可观测 | structlog；`/scheduler/status`；数据覆盖 `GET /market/freshness/coverage` |
| 测试 | pytest ~330 用例（conftest 自动建 `airesearch_test` 库，拒绝连开发库；embedding 用确定性假向量，不依赖 Ollama）；ruff 仅改动文件；**测试与实盘运行严禁并发**（pytest 会清 dev 库 screener 表） |

## 8. 已裁剪模块（瘦身全记录）

| 轮次 | 删除内容 | 提交 |
|---|---|---|
| 2026-11-24 一次瘦身 | research / portfolio / ai / dashboard 模块 | 多提交 |
| 2026-11-25 二次瘦身 | 组合/再平衡、表现跟踪与快照、回测交互路由（引擎保留）、freeform 模式、运行取消、近似命中；预设只读化；fact_checks 建立；报告四段化；前端收缩 | b0a2bed..210946a |
| 2026-11-25 三次简化 | **LLM 深判整体退役**（judge/judge_eval/eval/证据守卫）、变化日报+Webhook、回测 service 层（状态机+任务 handler）、CSV 导出/自选推送端点、15 个排查脚本归档 | 5fc43f3..7f6494d |
| 2026-11-26 六次简化 | **知识库问答退役（全系统零 LLM：adapters/llm.py、llm_usage.py、LLM 协议与配置）**、公司中心退役（删 CRUD/thesis/自选，只留 GET /companies）、news_service 删除、ScreenerBacktestRun ORM 删除（表保留）；**券商 cash_coverage 豁免修复**（exempt 态）、报告轮次对比、confidence 退役、预设证据分层（grade 徽标 + 定时默认改 financial,value） | 4105dd4..abc90c4 |
| 2026-11-26 七次简化 | **task_manager 持久任务队列退役**（后台协程直跑，删 tasks/retry 端点）、事件查询/清理 API 删除（event_log 只写保留）、比率层+估值分位整链删除（ratio_service/routes/前端 hook）、profile 摄取链删除（3 端点+service）、company_tags 空壳+openapi.json+generate_openapi.py 删除、Makefile 坏目标清理、**测试假向量化解耦 Ollama**（4 个环境豁免转绿） | a6ae52f..5812914 |

> 七次简化设计：`2026-11-26-infra-deadlink-cleanup-design.md`（S1.3 DI getter 勘察结论：10/10 均有消费方，无可删）。

回捡方式：`git revert` 对应提交；DB 表全部保留。

## 9. 已知架构级缺口 / 下一步

1. **估值规则分位数化**：硬编码绝对阈值（pe<25）改为行业分位数（industry_ranking 数据已有）
2. 回测市值用「当前总股本 × 历史价」近似，频繁再融资公司有偏差
3. 数据源单点：财务依赖东财
