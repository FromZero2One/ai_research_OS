# AI Research OS — Backend

Python/FastAPI 后端。完整使用手册见根目录 [`USAGE.md`](../USAGE.md)。

## 技术栈

- **框架**: FastAPI + async SQLAlchemy + Pydantic v2
- **存储**: PostgreSQL（多 schema + pgvector）+ Qdrant（向量）+ Redis（缓存）
- **AI**: DeepSeek（OpenAI 兼容，本机默认）/ Ollama（本地 LLM + Embedding）
- **数据源**: akshare 子进程直连（A股/港股，Tencent/Sina/Eastmoney），yfinance（美股备选）
- **质量**: pytest 390+ 用例 + ruff + mypy + pre-commit

## 架构

5 个业务模块 + Screener，依赖只向上：

```
Company → Market + Document → Knowledge(RAG) → Screener(筛选/深判/回测)
```

> 2026-11-24 瘦身：research/portfolio/ai/dashboard 四模块代码已删除（数据库表保留）。LLM 用量端点 `/api/v1/ai/usage` 由 `core/system_routes.py` 继续提供。

各模块文件结构并不完全统一：

| 形态 | 模块 |
|------|------|
| 完整四层 `models → schemas → service → routes` | company, document |
| `service/` + `routes/` 子目录拆分 | market（另含 domain/repositories/akshare_executor） |
| 薄模块（仅 routes + service，无自有 models/schemas） | knowledge（读写 document 表 + Qdrant） |
| 编排型（pipeline + LLM 两层） | screener（criteria/translate/screening/judge/report/service） |
服务通过 `core/container.py` DI 容器懒加载，路由经 `Depends(get_container)` 获取。

### Screener（智能选股，2026-10-21 v1；2026-10-22 v1.5 预设库）

两种选股模式（`POST /screener/runs` 的 `mode`）：

**freeform（v1）**：用户维护 `screener/criteria.md` 自然语言选股标准，手动触发：
① LLM 翻译标准为结构化规则（`ScreenerRule` 按 doc_hash 缓存，标准不变零 LLM 调用）
→ ② 确定性初筛（全市场快照 + 股票池过滤 + 量化规则求值 + 排名截断）
→ ③ LLM 逐只深判候选（单只失败隔离，结果落 `ScreenerJudgement` 供后续回测）
→ ④ Markdown 报告落 `screener/reports/`。

**presets（v1.5）**：预设标准库驱动，零 LLM 翻译。指标定义在 `screener/seeds.py`（42 个标准化指标，含 PE/PB/PS 派生估值、TTM 现金流质量、ROIC/FCFF/利息保障等因子，以及银行/保险专属指标）+ 8 套内置预设（核心资产/高成长/深度价值/GARP/周期反转 + 金融价值/银行价值/保险价值，只读；用户可自建）。触发时传 `preset_ids` + `combine`（union/intersection/flatten），规则纯确定性组装（`compose.py`），报告标注每只候选命中的预设（`[预设名]` 前缀 + snapshot `hits`/`presets`）。前端 `/screener` 有模式切换 + PresetManager 抽屉。

估值与质量指标由 `screener/valuation.py` 即时派生：PE/PS 优先 TTM（上年年报 + 本期累计 − 上年同期；历史期缺失回退单期年化），PB = 市值 / (总资产−总负债)；盈利质量 = TTM 经营现金流/净利润、TTM 经营现金流/营收、应计比率；PEG = PE / 净利同比，FCF 收益率 = FCFF / 总市值。F10 主要指标另提供 ROIC、利息保障倍数、现金比率、FCFF、现金流/营业利润、实际税率、有息负债率。历史期可用 `scripts/backfill_financial_periods.py` 回补（如 2025Q1–Q4）。深判已接入知识库检索并对无证据命中做确定性降级；无定性标准时跳过 LLM。财务数据由 `core/financial_sync.py` 在工作日 3:15 定时刷新（`FINANCIAL_DATA_SCHEDULE`）。

股票池入口统一做风险卫生过滤：ST/*ST/退市、停牌/无行情、换手率低于 `SCREENER_MIN_TURNOVER`、总市值低于 `SCREENER_MIN_MARKET_CAP`；报告附「股票池卫生过滤」统计。

行业分类存 `market.stock_industry`（申万一级 31 个行业为主，新浪行业补缺；覆盖 5,663 只 A 股，主板 2,111/2,111）。选股候选携带 `industry`/`sector`，报告与深判上下文均展示行业。工业预设自动排除金融股（流动比率/毛利率/周转率口径不适用），`金融价值` 预设只筛选银行/非银金融。入库脚本：`scripts/ingest_industry_sw.py`（主）与 `scripts/ingest_industry_sina.py`（补缺）。

行业相对排名：候选在其行业内计算 ROE/ROIC/营收增长/净利增长/现金流质量/PE/PB 分位（金融行业用 PE/PB/ROE），综合为 `industry_score`；排序在筛选得分之后、市值之前使用；单行业候选上限 `SCREENER_MAX_PER_INDUSTRY`（默认 8）。报告与深判上下文展示行业分位。

近似命中（2026-10-24）：报告附「近似命中（仅差 1 条规则）」——在股票池中恰好只有一条量化规则未满足、且无缺失数据的票（按市值降序取前 10）。union 模式对每个预设分别判断并去重；缺数据或失败 ≥2 条规则不列入，避免噪声。用于人工复核“被规则门槛卡掉的次优标的”，不影响候选池与推荐。

行业专属指标（F10）：银行侧净息差、不良贷款/贷款总额、不良率、拨备率、一级资本充足率；保险侧净投资收益率、已赚保费、偿付能力充足率。SW 一级行业把保险与券商同归“非银金融”，服务层用 F10 保费/贷款字段进一步区分 `financial_type`，银行/保险预设据此只筛对应子行业。

LLM 只在深判参与，筛选执行确定性。迁移 `b5d2f8a3c6e1` → `c8e1b7d4f2a9` → `b7c8d9e0f1a2` → `c1d2e3f4a5b6` → `d2e3f4a5b6c7` → `e3f4a5b6c7d8` → `f4a5b6c7d8e9` → `a5b6c7d8e9f0` → `b6c7d8e9f0a1` → `c7d8e9f0a1b2` → `d8e9f0a1b2c3` → `e9f0a1b2c3d4`，schema `screener`。

### 预设回测（2026-10-23 MVP）

用历史数据验证预设的历史表现（`POST /screener/backtests`，body: `preset_id` + `years` 1-10；`GET /screener/backtests/{id}` 查结果）。

- **状态机**：`pending → running → completed/failed`（`screener.backtest_runs` 表），经持久任务 `screener_backtest` 后台执行，同时刻至多一个进行中（409）
- **数据**：日线走外部 MySQL 前复权库（`BACKTEST_MYSQL_URL`，仅存 .env），**逐只「边拉边灌」**——单票一次查询（~1200 行）立即落库 commit，本地行数即进度、≥200 根视为完整可断点续传、单票网络错误重试 3 次；同票同日重复行去重、(ticker,date) 唯一约束幂等；历史财务缺失报告期按需补拉 **四类 loader**：`ingest_marketwide_yjbb`（利润表）+ `ingest_marketwide_zcfz`（资产负债表）+ `ingest_marketwide_xjll`（现金流量表）+ `ingest_marketwide_main_finance`（F10，ROIC/FCFF 等），单类 SAVEPOINT 隔离；完整性判定要求 `eps`+`total_assets`+`operating_cash_flow` 且至少一个 F10 标记指标（roic/fcff/current_ratio）。**票池**：活跃公司（自选）<100 只时使用外部库全市场 symbol（`stock_name_entity`，5,386 只，毫秒级，进程内缓存）——预设回测面向全市场，自选票池仅用于个人组合回测
- **口径**（`screener/backtest.py` 纯函数）：调仓日 = 各披露截止日（Q1 4-30 / Q2 8-31 / Q3 10-31 / 年报次年 4-30）后首个交易日；**4 月调仓统一用上一年年报**，无未来函数；收益一律前复权 close；停牌（成交量为 0）按不可交易记 0 并标注；近似市值 = 调仓日收盘价 × 当前总股本；**已计佣金/卖出印花税/单边滑点**（`BACKTEST_COMMISSION_RATE` / `BACKTEST_STAMP_DUTY_RATE` / `BACKTEST_SLIPPAGE_RATE`）
- **产出**：result JSON `{summary: {total_return, cagr, bench_cagr, excess_cagr, max_drawdown, annual_volatility, sharpe, sortino, calmar, win_rate, split_sample, ...}, yearly: [...]}` + Markdown 报告落 `screener/reports/`（含免责声明）。风险指标按季度收益年化（×√4），无风险利率由 `BACKTEST_RISK_FREE_RATE` 配置。
- **分段稳健性**：`split_sample` 把调仓期按时间对半切分，分别给出年化/基准/超额/回撤/胜率与 `consistent_excess`（两段是否都跑赢）；报告新增「分段稳健性」表。期数 <4 不输出。注意：回测不做参数优化，对半切分只是稳健性观察，不等同严格样本外验证。
- **API/UI**：`GET /screener/backtests`（最近 50 次，含预设名与 summary）、`GET /screener/backtests/{id}`、`GET /screener/backtests/{id}/report`。前端选股页「预设回测」卡片可选预设/年数启动回测（后台任务），展示汇总指标、分段表与逐年明细。
- **运行前提**：`BACKTEST_MYSQL_URL` 必须在 `backend/.env` 配置，否则后台任务会以“未配置，无法拉取历史日线”失败。回测 handler 在 app lifespan 启动 worker 前显式注册，避免 `No handler registered`。
- 已知近似：外部库无历史股本 → 市值为近似值；**PIT 用法定披露截止日口径**（东财 yjbb「最新公告日期」为滚动最新值、无法用于历史期，故将公告日钳制到报告期截止日；报告期截止日 ≤ 调仓日才可见，无前视）；涨跌停不可交易未单独建模。报告内均已声明。
- **首份有效成绩**（2026-10-25，3 年 / 9 个季度调仓期 / 基准 CSI300 CAGR +6.39%）：高成长 +23.84%（超额 +17.45%）、金融价值 +16.01%（超额 +9.61%、Sharpe 0.90）、周期反转 +2.65%、深度价值 -1.31%、核心资产 -8.37%、GARP -16.37%。全部 6 套均无空仓期。

### 定时筛选与变化日报（2026-10-24）

`core/screener_schedule.py` 在工作日 16:30（收盘后）按 `SCREENER_SCHEDULE_PRESETS`（默认 `core`）依次运行预设；已有进行中的 run 时跳过。每轮完成后与「相同 mode/combine/preset_ids（freeform 用 criteria_hash）」的上一轮 completed run 对比，只输出变化：新推荐/掉出推荐/新进候选/移出候选，Markdown 落到 `screener/reports/YYYY-MM-DD-diff-<run8>.md`，并写 `screener.diff` 事件。

API：`GET /api/v1/screener/runs/{run_id}/diff` 返回变化日报 Markdown 与 `has_previous`；前端历史运行表新增「日报」按钮。手动触发调度：`POST /api/v1/scheduler/run/screener_schedule`。

**任意两轮对比（2026-10-24）**：`GET /api/v1/screener/runs/{run_id}/diff?base_run_id={id}` 可指定任意已完成运行作为基线（默认仍自动找同口径上一轮）；基线不存在 → 404，基线与当前相同 → 422，基线未完成 → 返回说明文本。前端日报面板新增基线下拉框。
**口径审计（2026-10-24）**：预设被编辑后 preset_ids 不变，仅按 id 找基线会把旧规则运行误当同一口径。现在 `diff_service` 对 `run.rules` 做稳定哈希（忽略展示用 `preset_names`），只与规则指纹一致的历史运行对比；若同 ids 的历史运行规则已变，则本轮作为新基线，日报明确写「规则已变更，历史运行不可比」。

**取消运行（2026-10-24）**：`POST /api/v1/screener/runs/{run_id}/cancel` 将进行中的运行置为 `cancelling` 并设置进程内取消事件；worker 在阶段边界以及每只深判开始前检查，命中后停止剩余 LLM 调用、清空未完成结果并把状态落为 `cancelled`（不生成报告）。排队中的运行在 worker 启动时直接收尾；已结束的运行返回 409，重复取消幂等。前端历史运行表对进行中的行显示「取消」按钮。取消是 cooperative 的：已在途的单次 LLM 请求会在完成或取消信号到达后尽快返回。
**Webhook 通知（2026-10-24）**：配置 `SCREENER_WEBHOOK_URL` 后，定时任务在变化日报生成后推送摘要（新推荐/掉出推荐/新进候选/移出候选 + 股票名单 + 日报路径）。`SCREENER_WEBHOOK_FORMAT` 支持 `wecom` / `feishu` / `dingtalk` / `generic`（默认通用 JSON，群机器人直接选前者）。`SCREENER_WEBHOOK_NOTIFY_ON=changes`（默认）仅在有变化时发送，`always` 每轮都发；业务错误码（如企微 `errcode!=0`）按失败记录，通知失败不会中断定时任务。发送结果在调度返回的 `notification` 字段中可见。

**失败告警（2026-10-24）**：同一 Webhook 也用于运行失败告警——手动/定时 run 失败（`screener.failed`）以及定时任务自身异常都会推送「标准 / Run / 时间 / 错误」摘要；未配置 URL 时静默跳过，告警失败不影响运行结果。

**调度状态与手动运行（2026-10-24）**：`GET /api/v1/screener/schedule` 返回 cron、定时预设、下次运行时间、Webhook 配置；`POST /api/v1/screener/schedule/run` 以持久任务 `screener_schedule` 后台执行一轮定时选股（不阻塞 HTTP，重复提交返回 409）。前端选股页「定时任务」卡片展示这些信息并提供「立即运行定时选股」。调度配置本身仍来自环境变量（`SCREENER_SCHEDULE` / `SCREENER_SCHEDULE_PRESETS`），UI 只读。

**结果导出（2026-10-24）**：`GET /api/v1/screener/runs/{run_id}/export` 导出该轮全部判断为 CSV（UTF-8 BOM，Excel 直接打开），含结论/推荐/置信度/行业/价格/市值/初筛得分/命中预设/理由/标准命中/错误；前端历史运行表「CSV」按钮。

### 三态结论与置信度（2026-10-24）

`ScreenerJudgement.verdict` 区分四种结论：`recommend` / `reject` / `insufficient` / `failed`。证据守卫降级、资料不足或命中“数据不足”原因时记为 `insufficient`；显式不满足标准记为 `reject`。报告拆分为「未通过标准（未推荐）」与「数据不足（未推荐）」两个分区，API 同步透出 `verdict`。

`SCREENER_MIN_CONFIDENCE`（默认 0，即不启用）大于 0 时，置信度低于阈值的推荐会自动转为 `insufficient`。

### 定性选股前置：知识库文档（2026-10-24）

含定性标准的预设依赖知识库检索。知识库为空时，证据守卫会把文档类命中判为“数据不足”，预设会稳定 0 推荐（核心资产等纯量化预设不受影响）。报告概览会明确提示“知识库为空”。

使用步骤：文档中心上传年报/公告/研报 → 关联公司 → 等待后台索引完成（`is_indexed=true`）→ 再运行深度价值/GARP/周期反转/高成长/银行/保险等含定性标准的预设。

### LLM 深判评测（2026-10-24）

`screener/eval/judge_cases.jsonl` 内置 10 个标注用例：无资料文档类标准、财务可验证标准、带资料片段且要求引用、混合标准。`scripts/eval_judge.py` 调用真实 LLM 跑 `judge_one`，输出 JSON 合法率、推荐判定匹配率、证据纪律违规数、自动降级数与平均耗时，报告落 `screener/reports/eval-judge-*.md`。

```bash
cd backend
ALL_PROXY= all_proxy= PYTHONPATH=. ./.venv/Scripts/python.exe -X utf8 scripts/eval_judge.py
```

本地 qwen3.5-q4 基线：JSON 合法率 100%、推荐匹配 7/7、证据违规 0、平均 9.1s。

### 组合构建（2026-10-24）

`POST /api/v1/screener/runs/{run_id}/portfolio`：把该轮**推荐股**按资金分配成组合。参数：`capital`、`method`（equal/score/confidence）、`max_weight`、`max_industry_weight`、`max_holdings`。约束冲突时只向下收缩权重，剩余保留现金（不做杠杆），返回 `holdings`（代码/名称/行业/价格/权重/金额）、`invested`、`cash` 与 `warnings`。前端历史运行表新增「组合」按钮。

**组合持久化（2026-10-24）**：请求体加 `save: true` / `name` 可把参数与结果保存到 `screener.portfolios`（JSONB）并返回 `portfolio_id`；`GET /api/v1/screener/runs/{run_id}/portfolios` 列某轮已保存组合，`GET/DELETE /api/v1/screener/portfolios/{portfolio_id}` 查看/删除，`GET /api/v1/screener/portfolios` 列全部。前端组合面板新增「保存」按钮与已保存组合标签（点击载入、关闭删除）。迁移 `d8e9f0a1b2c3` 建表，并把 `cancelling` 纳入「同一时刻仅一个活跃 run」的唯一索引。

**组合再平衡（2026-10-24）**：`POST /api/v1/screener/portfolios/{portfolio_id}/rebalance`（body `tolerance` 默认 0.01、`lot_size` 默认 100）按最新收盘价估算持仓市值，与保存时的目标权重比较，返回每只当前/目标权重、漂移、`buy/sell/hold`、股数与金额建议。漂移在容忍度内持有；买入按整手向下取整（不足一手标记 `lot_blocked`）；缺最新价回退保存价并标记 `stale_price`、不给交易建议。前端载入已保存组合后可「计算再平衡」并查看建议表。

### 推荐后表现（2026-10-24）

`GET /api/v1/screener/runs/{run_id}/performance`：按 **T+1 收盘价**（运行日之后首个交易日）作为买入价，计算每只推荐股在 1/3/6/12 个月的收益与当前收益；等权汇总平均收益、胜率、样本数；同时拉沪深300同期限收益，汇总增加基准与超额（基准不可用时自动省略）。前端历史运行表新增「表现」按钮。日线覆盖不足的票标记 `no_entry_price`；随着行情采集推进覆盖率会提升。

**表现快照（2026-10-24）**：表 `screener.performance_snapshots`（迁移 `e9f0a1b2c3d4`，`(run_id, as_of)` 唯一）按自然日保存表现汇总与个股明细。`POST /api/v1/screener/runs/{run_id}/performance/snapshot` 计算并保存当日快照（同日重复调用幂等覆盖），`GET /api/v1/screener/runs/{run_id}/performance/history` 返回历史快照。`core/performance_schedule.py` 按 `PERFORMANCE_SNAPSHOT_SCHEDULE`（默认工作日 17:10）为最近 30 天完成的运行自动记录快照；也可用 `POST /api/v1/scheduler/run/performance_snapshot` 手动触发。前端表现面板新增「记录快照」与历史快照表。

### 数据质量前置检查（2026-10-24）

`GET /api/v1/screener/data-quality` 返回最新财务期与关键指标覆盖（ROE/营收/净利/经营现金流/总资产/ROIC/FCFF）、A 股公司行情覆盖（≥200 根日线）、最新行情日期、知识库文档/切片数，以及聚合告警（知识库为空、行情覆盖 <50%、财务库为空）。前端选股页「数据质量」卡片展示并高亮缺口；运行历史增加 全部/进行中/已完成/失败/已取消 筛选。

**加入自选（2026-10-24）**：`POST /api/v1/screener/runs/{run_id}/watchlist`（body 可选 `tickers` / `limit`）把该轮推荐股或指定 ticker 置为 `Company.is_active=True`，返回 `{added, already, missing}`；重复加入幂等，无公司记录的票进 `missing`。前端「运行明细」面板可逐只「自选」。

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

**实时深判（103 份年报入库后）**

| 预设 | 候选 | 推荐 | 拒绝 | 数据不足 | 可用性 |
|------|------|------|------|----------|--------|
| 高成长 | 46 | 15 | 0 | 31 | 可作候选池，需人工剔除软证据 |
| 深度价值 | 50 | 0 | 10 | 40 | 不可用（见下） |
| 金融价值 | 10 | 2（杭州银行 0.95、青岛银行 0.92） | 0 | 8 | 可直接参考 |

**深判证据链**：`screen` → 按标准逐条检索（`_retrieve_per_criterion`：每条标准 2 条、并发、交错合并、上限 8）→ 证据守卫（命中必须有 `[n]` 引用，否则降级）→ 三态结论。

- 逐条检索是必要的：单一 query（公司名 + 前两条标准）永远检索不到「审计意见」「分产品收入构成」这类具体章节。
- 但仍不够：实测检索已返回内控审计报告原文，模型仍答“未提及”；算现金覆盖率时拿总负债当短期负债。**事实性/合规性标准不应交给 LLM 判**，应改为文本匹配（是否含「标准无保留意见」/「立案调查」）+ 财务指标确定性判定，LLM 只保留叙事类判断（行业景气、竞争地位）。

**预设定性标准可验证性改造**：原标准（「细分行业排名前二」「行业渗透率持续提升」）年报几乎不会如此表述，导致高成长 46 只里 43 只判「数据不足」。已把 5 套预设的定性标准改写为「年报真实存在的章节/字段」，负向标准先锚定可引用正向证据（审计意见/监管指标）再谈未披露。备份 `data/presets_qualitative_backup.json`，脚本 `tools/rewrite_presets_qualitative.py`（`--apply` 才写库）。

**置信度语义**：`confidence` 是 LLM 对「该票应被推荐」的自评（0–1），**未校准、非概率**；实测集中在 0.95/0.92/0.85 三档。用途仅为排序与组合权重（`method=confidence`），不能当胜率。证据守卫会把被降级条目的 confidence 压到 ≤0.4；`SCREENER_MIN_CONFIDENCE > 0` 时低置信推荐转「数据不足」。校准方法：`GET /runs/{id}/performance` 按置信度分档对照实际 1/3/6/12 月收益。

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
| `screener` | screener_rules, screener_runs, screener_judgements, screener_metric_defs, screener_presets, screener_portfolios, performance_snapshots |

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
| | `OLLAMA_NUM_CTX` | 8192 | —（深判 prompt 含财务+多片段，默认 4096 会截断；仅 Ollama provider 生效） |
| Redis | `REDIS_URL` | redis://127.0.0.1:6380/0 | — |
| 文档 | `UPLOAD_DIR` / `MAX_UPLOAD_SIZE_MB` | data/uploads / 50 | — |
| | `CHUNK_SIZE` / `CHUNK_OVERLAP` | 512 / 64 | — |
| 市场 | `AKSHARE_ENABLED` / `YFINANCE_ENABLED` | true / true | — |
| 外部数据源 | `AKSHARE_MCP_DIR` | /home/wsm/codes/akshare_mcp 等 | 机器相关 |
| 调度器 | `SCHEDULER_ENABLED` | **true** | — |
| | `FINANCIAL_DATA_SCHEDULE` | `15 3 * * 1-5` | — |
| | `SCREENER_SCHEDULE` | `30 16 * * 1-5` | — |
| | `SCREENER_SCHEDULE_PRESETS` | `core`（逗号分隔 style_tag） | — |
| | `SCREENER_WEBHOOK_URL` | 空（禁用） | 企微/飞书/钉钉群机器人 URL |
| | `SCREENER_WEBHOOK_FORMAT` | `generic`（另支持 wecom/feishu/dingtalk） | — |
| | `SCREENER_WEBHOOK_NOTIFY_ON` | `changes`（或 `always`） | — |
| | `PERFORMANCE_SNAPSHOT_SCHEDULE` | `10 17 * * 1-5` | — |
| 回测 | `BACKTEST_COMMISSION_RATE` | 0.0003（单边万三） | — |
| | `BACKTEST_STAMP_DUTY_RATE` | 0.0005（卖出） | — |
| | `BACKTEST_SLIPPAGE_RATE` | 0.001（单边千一） | — |
| | `BACKTEST_RISK_FREE_RATE` | 0.02（年化） | — |
| 选股 | `SCREENER_MIN_TURNOVER` | 0.05（%） | — |
| | `SCREENER_MIN_MARKET_CAP` | 1e9（元） | — |
| | `SCREENER_MAX_PER_INDUSTRY` | 8（单行业候选上限） | — |
| | `SCREENER_MIN_CONFIDENCE` | 0（低于阈值转“数据不足”） | — |
| 安全 | `SECRET_KEY` | 每次启动随机生成 | — |

> **默认是 Ollama，本机跑 DeepSeek**：代码里 `LLM_PROVIDER` 默认 `ollama`，本机 `.env` 设为 `openai` + DeepSeek（`deepseek-chat`，OpenAI 兼容端点 `https://api.deepseek.com/v1`）；light tier（证据分类/事实抽取）同样走云端。
> 完整变量清单见 `core/config.py`。

## AI 能力

| 功能 | 所需服务 |
|------|---------|
| 公司/行情浏览 | 无 |
| 文档索引 | Embedding 需 Ollama（`OLLAMA_EMBEDDING_MODEL`，本机 bge-m3） |
| 知识库搜索 | 无（纯向量 + BM25，无需 LLM） |
| 知识库问答 / Screener 深判 | DeepSeek / Ollama / OpenAI |

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

APScheduler 定时任务（`core/scheduler.py`）：`market_data_update`（工作日 2:00）、`financial_data_update`（工作日 3:15，全市场财务三表刷新，三类数据源 SAVEPOINT 隔离）、`screener_schedule`（工作日 16:30，定时选股 + 变化日报）、`performance_snapshot`（工作日 17:10，最近运行表现快照）、`event_log_cleanup`（周一 3:00）。状态见 `GET /api/v1/scheduler/status`。

## 测试

```bash
make test        # pytest，专用 airesearch_test 库 + 隔离 Qdrant 集合
```
2026-11-24 瘦身删除了 research/portfolio/ai 相关用例（瘦身前 391 passed / 2 failed / 2 skipped，2 项失败为既有 research 证据继承用例）；screener + financial_sync 专项 **324 passed**。
