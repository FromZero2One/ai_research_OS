# Screener 预设回测 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 对单个预设做 5 年期、季度调仓的历史回测，产出汇总指标 + 逐年明细的 Markdown 报告。

**Architecture:** 纯函数回测核心（`backtest.py`，调仓日生成/单期选股/收益/净值指标）+ 数据准备层（`backtest_data.py`，外部 MySQL 前复权日线 + akshare 历史财务按期拉取）+ 编排服务（`backtest_service.py`，状态机 + task_manager handler）+ 报告渲染（`backtest_report.py`）。复用现有 `screening.evaluate_quant_rules`/`rank_candidates` 做选股。

**Tech Stack:** Python/FastAPI、SQLAlchemy async、PyMySQL（外部 MySQL，`asyncio.to_thread`）、akshare 子进程、PostgreSQL。

**Spec:** `docs/superpowers/specs/2026-10-23-screener-backtest-design.md`

## Global Constraints

- 调仓只用「调仓日前最近已披露完整报告期」的财务数据；4 月调仓统一用**年报**（N 年 Q4），不混用 Q1
- 收益计算一律用前复权 `close`（外部库已全 qfq）
- 历史市值 = 买入日收盘价 × 当前总股本（近似，报告声明）
- 外部 MySQL 凭据只存 `.env` 的 `BACKTEST_MYSQL_URL`，代码/文档不带明文；连接必须带 `connect_timeout`，走 `asyncio.to_thread`
- 外部日线灌库前按 (symbol, date) 去重；本地 `market.stock_prices` 加 (ticker, date) 唯一约束
- 调仓日序列从 `market.stock_prices` 实际日期推导；日历为空 → raise，不产出退化回测
- 回测不含 LLM 调用、不含定性条目、不含交易费用
- 测试库为 `airesearch_test`（conftest create_all），模型改动后旧测试库需 DROP 重建
- 本机禁止并行运行两个 pytest（表锁死锁）

## Review Focus

1. **未来函数**：选股用了调仓日之后才有的财务数据 → `test_no_lookahead_reuses_only_disclosed_period`（Task 3）钉住：调仓日 2022-05-10 只能见到 2021Q4 及更早
2. **重复日线行**：外部库同票同日多条 → `test_fetch_dedupes_rows`（Task 2）钉住：去重后 (symbol,date) 唯一
3. **空日历**：区间内无价格数据 → `test_empty_calendar_raises`（Task 3）钉住：raise 而非返回空调仓序列
4. **停牌收盘价缺失**：持有期区间无价 → `test_suspended_stock_zero_return`（Task 3）钉住：收益 0 + 明细标注 suspended
5. **除权失真**：若误用未复权价会产生幻影暴跌 → 全链路只用 qfq close，Task 2 灌库测试断言 close 值透传不自造

---

### Task 1: 数据模型 + 迁移 + 配置

**Files:**
- Modify: `backend/screener/models.py`（+`ScreenerBacktestRun`）
- Create: `backend/alembic/versions/f7a9c3e1b5d2_add_backtest_runs.py`
- Modify: `backend/alembic/versions/b5d2f8a3c6e1_add_screener_tables.py`（stock_prices 唯一约束不在此——见下）
- Create: `backend/alembic/versions/a1b2c3d4e5f6_add_stock_prices_unique.py`（`(ticker, date)` unique，schema market）
- Modify: `backend/core/config.py`（+`BACKTEST_MYSQL_URL: str = ""`）
- Test: `backend/tests/test_screener_backtest_models.py`

**Interfaces:**
- Produces: `ScreenerBacktestRun`（列：id/preset_id/years/status/error/result JSON/report_path/started_at/finished_at，schema screener）；`settings.BACKTEST_MYSQL_URL`

- [ ] **Step 1: 写失败测试** `tests/test_screener_backtest_models.py`：create 一行 backtest run（preset_id、years=5、status="pending"），flush 后查询断言列存在且默认值正确；断言 `market.stock_prices` 表约束含 `(ticker, date)` unique（用 `inspect` 检查 UniqueConstraint 存在即可，用 SQLAlchemy `Table` 元数据断言）

- [ ] **Step 2: 跑测试确认失败**（`pytest tests/test_screener_backtest_models.py -v`，ImportError/缺列）

- [ ] **Step 3: 实现**——`ScreenerBacktestRun` 模型仿照 `ScreenerRun` 风格（schema="screener"，UUIDMixin/TimestampMixin）；两个迁移手写（upgrade/downgrade 对称）；config 加 `BACKTEST_MYSQL_URL`

- [ ] **Step 4: 重建测试库并跑通过**——`DROP DATABASE airesearch_test` 后重跑测试（模型加列/新表，conftest create_all 才会重建）；再 `alembic upgrade head` 升开发库

- [ ] **Step 5: Commit** `feat(screener): backtest run model + stock_prices unique constraint`

### Task 2: 数据准备层（外部 MySQL 日线 + 历史财务）

**Files:**
- Create: `backend/screener/backtest_data.py`
- Test: `backend/tests/test_screener_backtest_data.py`

**Interfaces:**
- Consumes: `settings.BACKTEST_MYSQL_URL`；`screener.ingest` 的 yjbb/F10 拉取函数；`upsert_metrics_batch`
- Produces:
  - `fetch_daily_from_mysql(tickers: list[str], start: date, end: date) -> dict[str, list[dict]]`（每条 `{date, open, high, low, close, volume}`，按 (symbol,date) 去重、date 升序；外部库 `akshare.stock_history_daily_info_entity`，adjust='qfq'；PyMySQL + `asyncio.to_thread`，`connect_timeout=10`）
  - `sync_daily_to_pg(db, daily: dict[str, list[dict]]) -> int`（灌 `market.stock_prices`，幂等：先删同 ticker 同日期范围再插入；返回行数）
  - `ensure_financial_periods(db, periods: list[tuple[int, str]]) -> None`（对缺的报告期调 ingest 的 yjbb/F10 市场级拉取，SAVEPOINT 隔离单期失败）
  - `fetch_index_daily(start: date, end: date) -> list[dict]`（沪深300 `stock_zh_index_daily` symbol="sh000300"，`{date, close}` 列表）

- [ ] **Step 1: 写失败测试**——monkeypatch PyMySQL 连接为一个 fake cursor（返回预置行，含**同票同日重复行**），断言 `fetch_daily_from_mysql` 返回去重后升序结构；`sync_daily_to_pg` 用 test_session 断言行数与 close 值透传（不自造价格）；`ensure_financial_periods` monkeypatch ingest 函数断言对缺失期调用、对已有期不调用

- [ ] **Step 2: 跑测试确认失败**（ModuleNotFoundError）

- [ ] **Step 3: 实现** `backtest_data.py`（SQL 按日期范围+symbol 过滤分块拉取；`SELECT symbol,date,open,close,high,low,volume FROM ... WHERE symbol IN (...) AND date BETWEEN %s AND %s AND adjust='qfq'`）

- [ ] **Step 4: 跑测试通过**

- [ ] **Step 5: 真库冒烟（手动，不进 CI）**——`python scripts/demo_backtest_data.py` 拉贵州茅台 2021-01~2021-06 日线打印行数与首尾日期

- [ ] **Step 6: Commit** `feat(screener): backtest data layer (external MySQL qfq daily + historical financials)`

### Task 3: 回测核心（纯函数）

**Files:**
- Create: `backend/screener/backtest.py`
- Test: `backend/tests/test_screener_backtest_core.py`

**Interfaces:**
- Consumes: `screening.evaluate_quant_rules` / `screening.rank_candidates`（现有签名）；`market.domain.FinancialMetricEntry`
- Produces:
  - `build_disclosure_map() -> dict[tuple[int,str], date]`：报告期 → 披露截止日（Q1→4-30 当年、Q2→8-31 当年、Q3→10-31 当年、Q4→次年 4-30）
  - `generate_rebalance_dates(price_dates: list[date], start: date, end: date) -> list[date]`：每个披露截止日（落在区间内）后的首个交易日，**升序去重**；price_dates 为空 raise `ValueError("无价格日历")`
  - `pick_financial_period(asof: date) -> tuple[int, str]`：asof 日前最近**已完整披露**的报告期；4-30~8-30 窗口用上一年 Q4（年报优先，不混 Q1）
  - `select_portfolio(rebalance_date, presets_rules, snapshot_rows, financials_by_ticker, limit=20) -> list[dict]`：snapshot_rows 为该调仓日的价格行（含近似 market_cap=close×shares），内部调 evaluate_quant_rules + rank_candidates
  - `compute_holding_returns(portfolio, buy_prices: dict[str,float], sell_prices: dict[str,float]) -> list[dict]`：缺卖出价 → return 0.0 + `"suspended": True`
  - `compute_nav_and_stats(period_returns: list[dict], bench_returns: list[dict]) -> dict`：累计收益、CAGR、最大回撤（调仓日净值）、逐年收益与超额、年度胜率
- 返回的 result JSON 形状：`{"summary": {...}, "yearly": [{"year": 2022, "return": 0.12, "bench": 0.05, "excess": 0.07, "holdings": [...]}]}`

- [ ] **Step 1: 写失败测试**（每函数至少 1 例；重点用例按 Review Focus 1/3/4）：
  - `test_no_lookahead_reuses_only_disclosed_period`：调仓日 2022-05-10 → `pick_financial_period` 返回 (2021, "Q4")
  - `test_empty_calendar_raises`：price_dates=[] → pytest.raises(ValueError)
  - `test_suspended_stock_zero_return`：sell_prices 缺该票 → 收益 0 且 suspended=True
  - `test_generate_rebalance_dates`：构造 2021-01~2022-12 的价格日历，断言调仓日为各截止日后首个交易日且升序去重
  - `test_nav_stats`：构造 4 期已知收益序列断言累计/CAGR/最大回撤数值精确
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现** `backtest.py`（全部纯函数，无 IO）
- [ ] **Step 4: 跑测试通过**
- [ ] **Step 5: Commit** `feat(screener): backtest core (rebalance dates, portfolio selection, nav stats)`

### Task 4: 编排服务 + API + 报告

**Files:**
- Create: `backend/screener/backtest_service.py`、`backend/screener/backtest_report.py`
- Modify: `backend/screener/routes.py`（+`POST /screener/backtests`、`GET /screener/backtests/{id}`）
- Modify: `backend/core/container.py`（如需注册 service；仿照 screener service 注册方式）
- Test: `backend/tests/test_screener_backtest_api.py`

**Interfaces:**
- Consumes: Task 2 数据函数、Task 3 纯函数、`ScreenerBacktestRun`、`core.task_manager.create_task/register_handler`（模式同 `screener/service.py`）、`CriteriaPreset`
- Produces: `run_backtest(db, run_id) -> ScreenerBacktestRun`（状态机 pending→running→completed/failed；失败落 error 并 EventLogger 记录，模式同 run_screener）；`build_backtest_report(run, preset, result) -> str`；路由 `POST /api/v1/screener/backtests`（body `{preset_id: uuid, years: int=5}`，预设不存在→422，已有 running→409）

- [ ] **Step 1: 写失败测试**——monkeypatch Task 2 数据函数（返回小规模预置日线/财务 2 只票 × 4 个调仓期）+ FakeLLM 不需要（回测无 LLM）；POST 触发 → 直接调 `run_backtest` → 断言 status=completed、result JSON 含 summary/yearly、report_path 文件存在且含「预设回测报告」「未计交易费用」「市值近似」字样；preset 不存在 → 422；无日线数据（fetch 返回空）→ status=failed 且 error 非空
- [ ] **Step 2: 跑测试确认失败**
- [ ] **Step 3: 实现**——`backtest_service.py`（`run_in_background` handler 注册 `"screener_backtest"`）、`backtest_report.py`（Markdown 渲染，结构按 spec）、routes 两个端点（409/422 语义仿照 `trigger_run`）
- [ ] **Step 4: 跑测试通过**；再跑 `tests/test_screener_api.py` 确认无回归
- [ ] **Step 5: Commit** `feat(screener): backtest orchestration, API endpoints and markdown report`

### Task 5: 端到端真实冒烟 + 文档

**Files:**
- Create: `backend/scripts/demo_backtest_run.py`
- Modify: `README.md`（Roadmap 表「预设回测」标 ✅ 2026-10-23 + 简述）、`backend/README.md`（screener 节加 backtest 段落）、`memory/ai-research-os-session.md`（变更日志 + 完成度表智能选股行）

- [ ] **Step 1: 写 demo 脚本**——对「深度价值」预设跑真实回测（外部 MySQL 日线 + akshare 历史财务 5 年），打印 summary 与报告路径；脚本需人工运行，超时设 0（background 或手动）
- [ ] **Step 2: 人工运行验证**——报告文件生成、summary 数值合理（非 NaN、年份覆盖 5 年）
- [ ] **Step 3: 更新三份文档并 Commit** `docs: screener backtest MVP shipped + session memory`

---

## Self-Review 结论

- 规格覆盖：spec 的流程 6 步 → Task 2（数据①）、Task 3（②③④）、Task 4（⑤⑥）；汇总指标/报告结构/数据守则均落在对应任务测试里 ✅
- 类型一致性：`pick_financial_period` 返回 `(int, str)` 在 Task 3 定义、Task 4 消费；result JSON 形状两处一致 ✅
- Review Focus 5 项均有钉住测试 ✅
- 比例：计划 ≈ 规格 ×1.2，无函数体转录 ✅
