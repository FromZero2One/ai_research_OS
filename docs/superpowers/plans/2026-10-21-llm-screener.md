# LLM 智能选股器（Screener）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户维护自然语言选股标准文档，手动触发筛选：LLM 翻译标准 → 确定性初筛 → LLM 逐只深判 → 输出带标准吻合度说明的 Markdown 报告。

**Architecture:** 新建 `backend/screener/` 模块（models/domain/criteria/translate/screening/judge/report/service/routes），复用 core 的 LLM 适配器、任务系统、DI 容器、事件日志，复用 market 的 akshare 子进程模式与 financial 数据，复用 knowledge 的 RAG 检索。前端新增 `/screener` 页面。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 async + Alembic；pytest（需 docker postgres）；Vue 3 + Element Plus + TanStack Vue Query。

**Spec:** `docs/superpowers/specs/2026-10-21-llm-screener-design.md`

## Global Constraints

- 全中文注释/UI；注释风格与现有文件一致（中文 docstring + 行内说明）
- 迁移基于 head `a9c4d7e2f1b8`，新 revision id 用 `b5d2f8a3c6e1`，down_revision 指向它
- 测试跑 pytest 需先起 docker postgres（`docker/docker-compose.yml`）；测试库由 conftest create_all 自动建表，**新 schema `screener` 需在迁移和 init.sql 中显式 `CREATE SCHEMA IF NOT EXISTS screener`**（conftest 走 create_all 不建 schema；若测试报 schema 不存在，在 conftest 的建表路径前补 `CREATE SCHEMA IF NOT EXISTS screener`，或模型建表前用 event hook —— 实现者按 conftest 实际结构选最简单的方式并验证）
- Python 3.14 全局环境（无 .venv），pytest 在 `backend/` 目录下运行 `python -m pytest`
- 预存失败 4 项（Ollama embeddings 环境依赖，涉及 document/knowledge 上传索引链路）
- LLM 调用走 `core/adapters/llm.py` 的 `create_llm()` + `LLMResponse`（结构化输出用 JSON Schema 方式，参考 `research/evidence_service.py` 的 `_CLASSIFY_SCHEMA` + `research/planner.py` 的解析模式）
- akshare 子进程调用走 `market/akshare_executor.py` 的 `run_akshare(code, env_args)`，ticker 经 `build_akshare_env` 作为环境变量传递（安全红线，参照 `test_akshare_safety.py`）
- 报告文件落 `backend/screener/reports/`（加入 `.gitignore`，报告不入库 git）
- 深判单只失败不导致整次运行失败；运行状态机 `pending → screening → judging → completed/failed`
- 候选上限默认 50，得分 = 命中条件数/适用条件数，同分按市值降序

## Review Focus

- 标准文档被用户改成无意义/矛盾文本 → 翻译步骤给出明确错误（run 置 failed，error 含 LLM 原因），不产生空推荐静默成功（Task 4 测试 pin）
- 全市场快照 akshare 失败 → run 置 failed 且 error 可读，不落半截报告（Task 6 测试 pin）
- 某候选财务数据缺失 → 按 missing_data_policy（默认 exclude）处理，且报告"数据缺失"一节列出被排除者（Task 5/7 测试 pin）
- 同一时刻重复触发 → 409，不产生并发运行（Task 9 测试 pin）
- 单只深判 LLM 返回坏 JSON → 该只标 failed，其余继续，运行仍 completed（Task 7 测试 pin）

---

### Task 1: 数据模型 + 迁移

**Files:**
- Create: `backend/screener/__init__.py`、`backend/screener/models.py`
- Create: `backend/alembic/versions/b5d2f8a3c6e1_add_screener_tables.py`
- Modify: `backend/alembic/env.py`（加 `from screener.models import *  # noqa: F401, F403`）
- Modify: `docker/init.sql`（加 `CREATE SCHEMA IF NOT EXISTS screener;`）
- Test: `backend/tests/test_screener_models.py`

**Interfaces:**
- Produces: `ScreenerRun`（字段：id、status[pending/screening/judging/completed/failed]、criteria_hash、criteria_text、rules JSONB、candidate_count、result_count、report_path、error、started_at、finished_at、TimestampMixin、UUIDMixin，`__table_args__ = {"schema": "screener"}`）；`ScreenerJudgement`（run_id FK ondelete CASCADE、ticker、name、recommend bool?、reasons JSONB、criteria_hits JSONB、confidence float?、snapshot JSONB、status[ok/failed]、error Text?）；`ScreenerRule`（doc_hash String unique、rules JSONB、criteria_text）

- [ ] **Step 1: 写失败测试** `tests/test_screener_models.py`：用 conftest 的 `db_session` fixture 插入一条 ScreenerRun + 一条 Judgement + 一条 Rule，读回断言字段与默认值（status 默认 pending、Judgement.status 默认 ok）
- [ ] **Step 2:** `python -m pytest tests/test_screener_models.py -v` → FAIL（ModuleNotFoundError: screener）
- [ ] **Step 3:** 实现 `screener/models.py`（照 `research/models.py` 风格）+ 迁移文件（op.execute("CREATE SCHEMA IF NOT EXISTS screener") + create_table 三张）+ env.py 导入 + init.sql
- [ ] **Step 4:** `python -m pytest tests/test_screener_models.py -v` → PASS；`alembic upgrade head` 在开发库执行成功
- [ ] **Step 5:** `git add backend/screener backend/alembic docker/init.sql backend/tests/test_screener_models.py && git commit -m "feat(screener): data models + migration"`

### Task 2: 标准文档读写 + 规则 schema 纯函数

**Files:**
- Create: `backend/screener/criteria.py`、`backend/screener/rules_schema.py`、`backend/screener/criteria.md`（内置一份中文示例标准，含股票池声明"股票池：全部A股"与 3-5 条量化/定性条件示例）
- Test: `backend/tests/test_screener_criteria.py`

**Interfaces:**
- Consumes: 无
- Produces: `criteria.py`: `read_criteria() -> str`、`write_criteria(text: str) -> None`、`criteria_path() -> Path`（文档固定在 `screener/criteria.md`，相对 backend 目录）；`rules_schema.py`: `hash_criteria(text: str) -> str`（sha256 前 16 位）、`RULES_JSON_SCHEMA: dict`（结构：`{stock_pool: {type: enum[all,main,chinext,star,watchlist], tickers: list[str]}，quant_rules: [{metric, op, value, missing_data_policy: enum[exclude,include]}]，qualitative_criteria: [str]}，candidate_limit: int`，metric 键枚举 = FinancialMetric 常用名 + ratio_service 比率键 + 行情快照字段 price/turnover/market_cap）、`validate_rules(obj) -> list[str]`（返回错误列表，空列表=合法）

- [ ] **Step 1: 写失败测试**：`read_criteria` 返回非空且含"股票池"；`write_criteria` 后再读一致（用 tmp 路径 monkeypatch）；`hash_criteria` 同文本同 hash、改文本变 hash；`validate_rules` 对缺 stock_pool、op 非法、metric 未知各返回错误，合法对象返回 []
- [ ] **Step 2:** 运行 → FAIL
- [ ] **Step 3:** 实现两个模块（`validate_rules` 按 RULES_JSON_SCHEMA 手写校验，不引入 jsonschema 依赖）
- [ ] **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat(screener): criteria doc IO + rules schema validation"`

### Task 3: 板块归属 + 股票池过滤（纯函数）

**Files:**
- Create: `backend/screener/pool.py`
- Test: `backend/tests/test_screener_pool.py`

**Interfaces:**
- Produces: `board_of(ticker: str) -> str | None`（"main"/"chinext"/"star"/None，规则：6 开头 main、0 开头 main、3 开头 chinext、68 开头 star，其余 None）；`filter_pool(spot: list[dict], pool: dict, watched_tickers: set[str]) -> list[dict]`（spot 项含 ticker/name/price/market_cap；pool 为 Task 2 的 stock_pool 结构；watchlist 池 = watched_tickers ∪ pool.tickers；非 A 股前缀直接排除）

- [ ] **Step 1: 写失败测试**：`board_of("600519")=="main"`、`("300750")=="chinext"`、`("688981")=="star"`、`("000001")=="main"`、`("AAPL") is None`；`filter_pool` 对 all/main/chinext/star/watchlist 各一例（watchlist 含文档 tickers 与 watched 并集）
- [ ] **Step 2:** FAIL → **Step 3:** 实现 → **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat(screener): stock pool filtering"`

### Task 4: LLM 标准翻译

**Files:**
- Create: `backend/screener/translate.py`
- Test: `backend/tests/test_screener_translate.py`

**Interfaces:**
- Consumes: `core/adapters/llm.py: create_llm()`（`await llm.chat(messages) -> LLMResponse`，解析参考 `research/planner.py`）；Task 2 的 `RULES_JSON_SCHEMA`/`validate_rules`
- Produces: `async def translate_criteria(llm, criteria_text: str) -> dict`（返回通过 validate 的规则 dict；LLM 输出非法/校验不过时重试 1 次，仍失败 raise `ValueError(详情)`）；`async def get_or_translate_rules(db: AsyncSession, criteria_text: str) -> dict`（查 `ScreenerRule.doc_hash` 命中直接返回，未命中调用 translate 后 upsert 缓存）

- [ ] **Step 1: 写失败测试**（mock LLM，参考 `test_ratio_service.py` 的 mock 模式）：合法 JSON → 返回规则 dict；首坏次好 → 重试后成功；两坏 → ValueError；缓存命中（预插 ScreenerRule）不调 LLM（计数器=0）；缓存未命中调一次并落 ScreenerRule
- [ ] **Step 2:** FAIL → **Step 3:** 实现（system prompt 用中文，要求输出符合 schema 的 JSON，原文标准全文放入 user 消息）→ **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat(screener): LLM criteria translation with hash cache"`

### Task 5: 确定性初筛

**Files:**
- Create: `backend/screener/screening.py`
- Test: `backend/tests/test_screener_screening.py`

**Interfaces:**
- Consumes: Task 3 `filter_pool`；`market/akshare_executor.py: run_akshare`；`market/domain.py: FinancialMetricEntry`
- Produces: `fetch_market_spot() -> list[dict]`（akshare `stock_zh_a_spot_em` 子进程：内嵌代码打印 `__R__:<json>`，字段映射 ticker(代码)/name(名称)/price(最新价)/turnover(换手率)/market_cap(总市值)，解析失败 raise `DataSourceError`，复用 `core/exceptions.py`）；`evaluate_quant_rules(candidates: list[dict], rules: list[dict], financials_by_ticker: dict[str, list[FinancialMetricEntry]]) -> tuple[list[dict], list[dict]]`（返回 (通过, 因缺数据被排除)；纯函数：逐条规则对快照字段或指标求值，op ∈ {">",">=","<","<=","=="}，missing_data_policy=include 时缺数据放行并计入命中，exclude 排除）；`score_candidate(hit: int, applicable: int) -> float`；`rank_candidates(passed: list[dict], limit: int = 50) -> list[dict]`（按 score 降序、同分 market_cap 降序、截断）

- [ ] **Step 1: 写失败测试**：`evaluate_quant_rules` 纯函数全覆盖（命中/不命中/缺数据 exclude 排除/include 放行/price 快照字段）；`rank_candidates` 排序与截断；`fetch_market_spot` 用 monkeypatch `run_akshare` 返回样例 `__R__:[...]` 验证映射，返回 None 时 raise DataSourceError
- [ ] **Step 2:** FAIL → **Step 3:** 实现（财务数据由 service 层查好传入，本模块不查库，保证可单测）→ **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat(screener): deterministic screening + ranking"`

### Task 6: 深判（LLM 逐只定性判断）

**Files:**
- Create: `backend/screener/judge.py`
- Test: `backend/tests/test_screener_judge.py`

**Interfaces:**
- Consumes: `knowledge/service.py: KnowledgeService.search(query, top_k)`（签名见 knowledge/service.py:216）；Task 2 的 `qualitative_criteria`
- Produces: `build_judge_context(candidate: dict, knowledge_snippets: list[str]) -> str`（纯函数：行情/指标快照 + 可选知识库片段拼中文上下文）；`JUDGE_SCHEMA: dict`（`{recommend: bool, reasons: [str], criteria_hits: [{criterion, hit: bool, evidence}], confidence: 0-1}`）；`async def judge_one(llm, candidate: dict, criteria: list[str], knowledge: "KnowledgeService | None") -> dict`（search 异常静默吞掉返回空片段；LLM 输出解析失败重试 1 次，仍失败 raise ValueError）；`async def judge_candidates(llm, candidates, criteria_text, knowledge=None) -> list[dict]`（逐只调用，**单只 ValueError 捕获 → 结果 dict 标 status="failed", error=原因，不中断循环**；成功的标 status="ok"）

- [ ] **Step 1: 写失败测试**（mock LLM + fake knowledge，knowledge.search 抛异常不影响）：`build_judge_context` 含 ticker 与片段；`judge_one` 正常返回结构化结果；坏 JSON 重试；`judge_candidates` 一只抛 ValueError 其余正常 → 全部有结果、失败者 status=="failed"、成功的 recommend 字段存在
- [ ] **Step 2:** FAIL → **Step 3:** 实现（judge prompt 中文：给定候选快照与定性标准逐条判断，只依据提供的上下文，不得编造数字）→ **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat(screener): per-candidate LLM judgement with failure isolation"`

### Task 7: 报告生成

**Files:**
- Create: `backend/screener/report.py`
- Test: `backend/tests/test_screener_report.py`

**Interfaces:**
- Consumes: Task 2 criteria_text、Task 5/6 的数据结构
- Produces: `build_report(run: dict, judgements: list[dict], criteria_text: str, excluded_missing_data: list[dict]) -> str`（纯函数，输出 spec §6 结构的 Markdown：概览/推荐列表表格/每只理由与 criteria_hits/**标准吻合度说明**（对照 criteria_text 的量化+定性条目逐条统计命中只数并给出代表例）/附：候选未推荐摘要/附：因数据缺失被排除列表）；`report_path_for(run_id: str) -> Path`（`screener/reports/YYYY-MM-DD-<run_id前8>.md`，日期取当天）

- [ ] **Step 1: 写失败测试**：给定两推荐一未推荐一缺失的 fixture，断言报告含"## 推荐列表"表格行、含每个 criteria_hit 条目、含"标准吻合度"节且逐条列出新标准、含"数据缺失"节列被排除 ticker、无推荐时输出"本次无推荐"
- [ ] **Step 2:** FAIL → **Step 3:** 实现 → **Step 4:** PASS
- [ ] **Step 5:** `git commit -m "feat(screener): markdown report generation with criteria conformance"`

### Task 8: 编排服务 + 后台任务 + 路由 + 容器注册

**Files:**
- Create: `backend/screener/service.py`、`backend/screener/routes.py`
- Modify: `backend/core/container.py`（加 `screener_service` property，模式照 ratio_service）、`backend/core/interfaces.py`（ScreenerService Protocol）、`backend/api/app.py:248-263` 附近（include screener_router）、`docker/docker-compose.yml` 不动（reports 目录挂载不需要，报告存本地）
- Test: `backend/tests/test_screener_api.py`

**Interfaces:**
- Consumes: Task 1-7 全部产出；`core/task_manager.py: register_handler(task_type, fn)`、`create_task(task_type, task_key, payload)`（返回 None=重复）；`create_llm()`；`EventLogger.record`
- Produces:
  - `ScreenerService(db: AsyncSession)`：`async def run_screener(run_id: uuid.UUID) -> None`（状态机推进：读 criteria → get_or_translate_rules → fetch spot → filter_pool → 批量查 PG financials（`select FinancialMetric where ticker in …`）→ evaluate + rank → judge_candidates → 逐条落 ScreenerJudgement → build_report 写文件 → run 收尾 completed（candidate_count/result_count/report_path）；任何未捕获异常 → status=failed + error）
  - `async def trigger_run(db) -> ScreenerRun | None`（创建 run 行 + `create_task("screener_run", "singleton", {"run_id": ...})`，任务重复时返回 None）
  - `register_handler("screener_run", handler)`（模块 import 时注册，handler 开 managed_session 调 run_screener，模式照 `document/tasks.py`）
  - routes：`POST /screener/runs`（201 返回 run 或 409 "已有筛选进行中"）、`GET /screener/runs`、`GET /screener/runs/{id}`（含 judgements）、`GET /screener/runs/{id}/report`（读文件，404 保护）、`GET/PUT /screener/criteria`、`GET /screener/rules`（最近一次 ScreenerRule）
- [ ] **Step 1: 写失败测试**（TestClient，monkeypatch `fetch_market_spot` 返回 3 只固定样例、mock LLM）：trigger → 轮询 run 直到 completed（测试内直接调用 handler 而非等 worker，参考 conftest 里同步执行任务的方式）→ 断言 run 字段、judgements 落库、report 文件存在且内容含推荐；重复触发 → 409；`GET /screener/criteria` 返回文档文本；`PUT` 后 `GET` 反映新文本；`GET /screener/runs/{id}/report` 返回 markdown
- [ ] **Step 2:** FAIL → **Step 3:** 实现 service/routes/container/interfaces/app 挂载 → **Step 4:** PASS；全量回归 `python -m pytest -x -q`（除 4 项预存 Ollama 失败外全绿）
- [ ] **Step 5:** `git commit -m "feat(screener): orchestration service + API + background task"`

### Task 9: 前端智能选股页

**Files:**
- Create: `frontend/src/views/Screener.vue`
- Modify: `frontend/src/stores/api.ts`（加 hooks）、`frontend/src/router/index.ts`（加 `/screener` 路由）、`frontend/src/components/Sidebar.vue`（navItems 加"智能选股"，图标 DataAnalysis）
- Test: `npx vue-tsc --noEmit` 零错误（人工核对渲染）

**Interfaces:**
- Consumes: Task 8 的 API
- Produces: `stores/api.ts` 新增：`useScreenerRuns()`、`useScreenerRun(id)`、`useTriggerScreenerRun()`（mutation）、`useScreenerCriteria()`/`useSaveCriteria()`、`useScreenerRunReport(id)`（返回 { report: string }）

- [ ] **Step 1:** `stores/api.ts` 按 `useList`/`useMutation` 现有泛型模式加 6 个 hooks（照文件内既有 hooks 风格）
- [ ] **Step 2:** 写 `Screener.vue`：三段布局 — ① 标准文档编辑（el-input textarea + 保存按钮，成功 ElMessage）② "开始筛选"按钮 + 运行中禁用 + el-progress 模拟状态轮询（run status 每 3s 轮询直到 completed/failed，复用 `useScreenerRun` 的 refetchInterval 模式）③ 最新报告 marked+DOMPurify 渲染 + 历史运行 el-table（时间/状态/推荐数/查看报告按钮）
- [ ] **Step 3:** router + Sidebar 注册
- [ ] **Step 4:** `npx vue-tsc --noEmit` → 零错误；`npm run dev` 打开 `/screener` 人工确认三段可交互
- [ ] **Step 5:** `git commit -m "feat(screener): frontend page with criteria editor and report viewer"`

### Task 10: 收尾

**Files:**
- Modify: `backend/screener/reports/.gitignore`（新建，内容 `*\n!.gitignore`）、`backend/README.md`（screener 模块一节）、`memory/ai-research-os-session.md`（变更日志 + 进度）

- [ ] **Step 1:** `.gitignore` 报告目录、README 补模块说明（表/API/流程一句话）、memory 快照更新（照既有变更日志格式）
- [ ] **Step 2:** 全量回归 `python -m pytest -q` → 与基线一致（168+ 新增通过，4 预存失败）
- [ ] **Step 3:** `git commit -m "docs: screener module readme + session memory"`
