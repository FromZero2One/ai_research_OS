# 价值推荐聚焦 · 二次瘦身 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把系统收敛为「每日自动产出 Markdown 价值推荐清单（股票+理由）」，砍掉组合/表现/回测UI/freeform/取消等枝叶，事实检查确定性化。

**Architecture:** 纯减法为主（删模块+测试），加法仅一处新文件 `screener/fact_checks.py` 与报告格式改造。DB 不迁移（表保留，只删 ORM 类注册）。前端收缩 Screener.vue 并删除三个页面。

**Tech Stack:** FastAPI + SQLAlchemy async + pytest（asyncio auto 模式）；Vue 3 + TanStack Query。

**Spec:** `docs/superpowers/specs/2026-11-24-slim-to-value-recommendation-design.md`

## Global Constraints

- 不做 alembic 迁移、不 drop 表；ORM 类删除后 `Base.metadata` 不再含它们即可。
- 每个任务完成后该任务范围的 pytest 必须绿；全部任务完成后全量 `pytest -v` 绿。
- ruff 只跑改动文件（repo 有历史债务，禁止全仓 format）。
- 提交信息用 conventional commits（本仓库 AGENTS.md 约定），straight to main，不 push。
- 后端命令一律从 `backend/` 目录用 `.venv\Scripts\python -m pytest`；测试前 docker Postgres+Qdrant 必须在跑。
- LLM/网络相关测试已 mock；不得新增真实 LLM/akshare 调用。

## Review Focus

- 删除后残留 import（`grep -r "portfolio\|performance\|cancel\|translate"` 在 backend+screener 内应为零误引）——每个删除任务的验证步包含 grep。
- 结构化 fact_check 条目混入字符串列表导致 `compose.py` f-string 崩溃——Task 7 测试覆盖 dict+str 混合输入。
- 事实检查「未找到证据」必须落 insufficient 而非 reject——Task 8 测试钉死。
- `service.py` translate 回路拆除后 preset 运行仍能产出 rules——Task 4 的端到端 mock 测试覆盖。
- 前端删除 Knowledge 页后 router/Sidebar/api.ts 无悬空引用——Task 10 以 `npm run build`（vue-tsc）为闸。

---

### Task 1: 删除组合构建与再平衡

**Files:**
- Delete: `backend/screener/portfolio.py`, `backend/screener/portfolio_store.py`, `backend/screener/rebalance.py`, `backend/screener/routes/portfolio.py`
- Modify: `backend/screener/routes/__init__.py`（移除 portfolio router）, `backend/screener/models.py`（删 `ScreenerPortfolio` 类；保留表）, `backend/screener/service.py`（如有 portfolio 引用）
- Delete tests: `backend/tests/test_screener_portfolio.py`, `backend/tests/test_screener_rebalance.py`

**Interfaces:**
- Produces: `routes/__init__` 中 portfolio router 移除；无保留代码依赖被删模块。

- [ ] Step 1: 删除上述 4 个源文件 + 2 个测试文件；从 `routes/__init__.py` 移除 import 与 include；从 `models.py` 删除 `ScreenerPortfolio`。
- [ ] Step 2: `grep -rn "portfolio" backend/screener backend/api` —— 仅允许命中 `backtest.py` 内部独立的 `select_portfolio`（回测引擎自有函数，保留）与 `routes/backtest.py` 中 portfolio 无关行；其余引用清零。
- [ ] Step 3: Run `cd backend && .venv\Scripts\python -m pytest tests/test_screener_api.py tests/test_screener_models.py -v` → PASS。
- [ ] Step 4: Commit `chore: 删除组合构建与再平衡模块`.

### Task 2: 删除表现跟踪与快照

**Files:**
- Delete: `backend/screener/performance.py`, `backend/screener/performance_service.py`, `backend/screener/performance_store.py`, `backend/screener/routes/performance.py`, `backend/core/performance_schedule.py`
- Modify: `backend/screener/routes/__init__.py`, `backend/screener/models.py`（删 `ScreenerPerformanceSnapshot`）, `backend/core/scheduler.py:82-89`（移除 `performance_snapshot` 注册）, `backend/api/app.py`（移除 `core.performance_schedule` 导入与相关行）
- Delete tests: `backend/tests/test_screener_performance.py`

- [ ] Step 1: 执行删除与引用清理（app.py 中 lifespan 的 import、scheduler jobs 列表项）。
- [ ] Step 2: `grep -rn "performance" backend/core backend/screener backend/api` → 除无关词（如注释）外零命中；`GET /scheduler/status` 的 jobs 不再含 performance_snapshot（由 Task 2 测试断言）。
- [ ] Step 3: Run `pytest tests/test_core.py -v` + `pytest tests/test_screener_api.py -v` → PASS。新增断言：在 `tests/test_core.py` 中加一个用例 mock `get_scheduler_status` 返回不含 `performance_snapshot`（若该函数难测，改为检查 `core/scheduler.py` 源码中无该字符串的朴素测试——按现有 test_core 风格从简）。
- [ ] Step 4: Commit `chore: 删除推荐后表现跟踪与快照`.

### Task 3: 回测交互层删除（引擎保留）

**Files:**
- Delete: `backend/screener/routes/backtest.py`
- Modify: `backend/screener/routes/__init__.py`（移除 router）
- Keep untouched: `backtest.py`, `backtest_data.py`, `backtest_service.py`, `backtest_report.py`, `tools/run_backtest_queue.py`
- Modify tests: `backend/tests/test_screener_backtest_api.py` 删除 HTTP 路由用例，保留/迁移 `run_backtest_by_id` 直调用例（若已有 service 层用例则只删路由用例）

**Interfaces:**
- Produces: 回测只能经 `backtest_service.run_backtest_by_id(run_id)` 或 task handler `screener_backtest` 触发；`tools/run_backtest_queue.py` 走 task 队列，不受影响（已核实）。

- [ ] Step 1: 删路由文件与 include；修剪 `test_screener_backtest_api.py` 中 TestClient 路由用例。
- [ ] Step 2: Run `pytest tests/test_screener_backtest_core.py tests/test_screener_backtest_data.py tests/test_screener_backtest_pit.py tests/test_screener_backtest_models.py tests/test_screener_backtest_report.py -v` → PASS。
- [ ] Step 3: Commit `chore: 回测降级为脚本命令，删除交互路由`.

### Task 4: 删除 freeform 模式与 translate 回路

**Files:**
- Delete: `backend/screener/translate.py`, `backend/screener/criteria.py`, `backend/screener/criteria.md`, `backend/screener/routes/criteria.py`
- Modify: `backend/screener/service.py` — 删 `params is None` 分支（`trigger_run` 改为 `params` 必填、非 presets 模式 422）；删 `:409-431` 的 translate 步骤，`compose_rules` 输出的 `quant_rules`/`qualitative_criteria` 直接进入 screening/judge；`run.rules` 存 compose 输出；`criteria_hash` 改为对 compose 输出的稳定哈希（沿用 `rules_schema.hash_criteria` 对序列化 JSON 取哈希）
- Modify: `backend/screener/routes/runs.py` — `POST /runs` 校验 body 必含 `mode="presets"`；删除 `GET/PUT /criteria`、`GET /rules`（在 routes/criteria.py 已整删）
- Delete tests: `tests/test_screener_translate.py`, `tests/test_screener_criteria.py`
- Modify tests: `tests/test_screener_api.py` 中 freeform 触发用例改为 422 断言；preset 运行用例保持通过（mock LLM 不再需要 translate 桩，删除对应 monkeypatch）

**Interfaces:**
- Consumes: `compose.compose_rules(presets, mode, combine, pool) -> dict`（含 `quant_rules`, `qualitative_criteria`, `sector_scope`, `candidate_limit`）——签名不变。
- Produces: `run_screener` 内部不再 import translate；`ScreenerRun.criteria_hash` 语义 = compose 输出哈希（diff_service 的基线匹配逻辑不变，天然兼容）。

- [ ] Step 1: 先改 `test_screener_api.py`：freeform 空 body → 断言 422；preset 全链路用例去掉 translate mock。运行确认 FAIL。
- [ ] Step 2: 执行删除与 `service.py`/`routes/runs.py` 改造（criteria_hash = `hash_criteria(json.dumps(compose_output, sort_keys=True))`）。
- [ ] Step 3: `grep -rn "translate\|criteria\.md\|read_criteria" backend/screener` → 零命中（`rules_schema` 内同名概念除外）。
- [ ] Step 4: Run `pytest tests/test_screener_api.py tests/test_screener_presets_run.py tests/test_screener_diff.py tests/test_screener_compose.py -v` → PASS。
- [ ] Step 5: Commit `chore: 删除freeform模式，预设为唯一运行入口`.

### Task 5: 删除运行取消机制（完整清扫）

**Files:**
- Delete: `backend/screener/cancel.py`
- Modify: `backend/screener/errors.py`（删 `ScreenerCancelled`）, `backend/screener/service.py`（删 cancel 导入 `:21`、`ACTIVE_STATUSES` 中 cancelling `:79`、`_check_cancelled` 调用点 `:390-399` 等）, `backend/screener/judge.py:471-497`（删 `should_stop` 参数与轮询，`judge_candidates` 签名去 `should_stop`）, `backend/screener/routes/runs.py`（删 `/cancel` 路由 `:209-`）, `backend/core/screener_schedule.py:18`（`_ACTIVE` 去 cancelling）, `backend/screener/models.py:27`（CHECK 去 `'cancelling'`）, `backend/tools/reset_stuck_runs.py`（SQL 去 `cancelled`）
- Modify: `backend/core/screener_schedule.py` webhook 失败路径如引用 cancelled 状态一并清理
- Delete tests: `tests/test_screener_api.py` 中 cancel 用例

- [ ] Step 1: 执行清扫；`judge_candidates` 保持顺序与失败隔离逻辑，仅去 should_stop。
- [ ] Step 2: `grep -rn "cancel\|cancell" backend/screener backend/core backend/tools` → 零命中。
- [ ] Step 3: Run `pytest tests/test_screener_api.py tests/test_screener_judge.py -v` → PASS。
- [ ] Step 4: Commit `chore: 删除运行取消机制`.

### Task 6: 删除近似命中（顺带修潜伏 ImportError）

**Files:**
- Modify: `backend/screener/screening.py`（删 `evaluate_near_misses`）, `backend/screener/compose.py`（删 `evaluate_near_misses_by_preset`——若存在；评审确认 `service.py:514` 导入的该函数不存在于 compose，属幽灵导入，删 service 调用点即修复）, `backend/screener/service.py`（删 union 分支 near-miss 调用 `:514` 附近）, `backend/screener/report.py`（删近似命中分区）
- Modify tests: `tests/test_screener_screening.py` 删 near-miss 用例；`tests/test_screener_compose.py` 同

- [ ] Step 1: 删除代码与用例；确认 union+qualitative 全链路测试存在且通过（若原本缺失——幽灵导入未被打过——在 `test_screener_compose.py` 补一条 union+qualitative 走通 `compose_rules`→mock 评估的用例）。
- [ ] Step 2: `grep -rn "near_miss" backend/` → 零命中。
- [ ] Step 3: Run `pytest tests/test_screener_screening.py tests/test_screener_compose.py tests/test_screener_report.py -v` → PASS。
- [ ] Step 4: Commit `chore: 删除近似命中并修复幽灵导入`.

### Task 7: 预设只读化 + compose 拆分 fact_checks 键

**Files:**
- Modify: `backend/screener/presets.py`（删 create/update/delete，保留 list/get 与 builtin 校验常量）, `backend/screener/routes/presets.py`（仅留 `GET /metrics`、`GET /presets`）
- Modify: `backend/screener/compose.py` — `compose_rules` 输出新增键 `fact_checks: list[dict]`；qualitative 条目中 dict（`{"type":"fact_check",...}`）拆出到该键，字符串条目维持原路径；union 模式下 dict 条目不加预设前缀（自带 check 名即可区分）
- Modify tests: `tests/test_screener_presets_api.py` 删 CRUD 写用例、保留 GET；`tests/test_screener_compose.py` 新增：dict+str 混合输入 → `fact_checks` 键含 dict 项、`qualitative` 仅含 str、union 前缀只作用于 str

**Interfaces:**
- Produces: `compose_rules(...) -> {..., "fact_checks": list[dict]}`；后续 Task 8 消费。

- [ ] Step 1: 先写 compose 失败测试（混合条目）→ FAIL。
- [ ] Step 2: 实现 compose 拆分；预设 CRUD 删除。
- [ ] Step 3: Run `pytest tests/test_screener_compose.py tests/test_screener_presets_api.py tests/test_screener_presets_service.py -v` → PASS。
- [ ] Step 4: Commit `chore: 预设只读化，compose拆分fact_checks通道`.

### Task 8: 事实检查确定性化 `fact_checks.py`

**Files:**
- Create: `backend/screener/fact_checks.py`
- Modify: `backend/screener/judge.py` — `judge_candidates`/`judge_one` 接收 `fact_checks` 参数；在 LLM 调用前执行确定性检查并写入 `criteria_hits`（结构 `{"check": ..., "result": "pass|fail|not_found", "evidence": "...", "citation": "[n]|null", "detail": "现金覆盖 1.8x > 1.0"}`）；verdict 规则：任一 fail → recommend=False/verdict=reject；任一 not_found → verdict=insufficient（优先级 reject > insufficient > LLM 结论）；LLM 仅收叙事标准与事实检查结果摘要（作为上下文，不允许其改判事实项）
- Modify: `backend/screener/seeds.py` — 深度价值/金融价值 qualitative 改写为结构化 fact_check 条目（audit_opinion / litigation / cash_coverage, threshold 从现文案提取）
- Create: `backend/scripts/reseed_builtin_presets.py`（调 `insert_builtin_seeds` 幂等重灌）
- Test: `backend/tests/test_fact_checks.py`（新建）

**Interfaces:**
- Consumes: `compose_rules` 的 `fact_checks: list[dict]`（Task 7）；knowledge 检索复用 `KnowledgeService.search(query, top_k, content_type)`（事实检查走轻量路径：top_k=3、无并发、单次/检查）。
- Produces: `run_fact_checks(checks: list[dict], knowledge: KnowledgeService, company_id: str, financials: dict) -> list[dict]`（返回顺序同输入；每项含 `check/result/evidence/citation/detail`）。

- [ ] Step 1: 写 `test_fact_checks.py` 失败用例：①审计段落命中「无保留意见」→ pass+引用；②命中「保留意见」→ fail；③检索零命中 → not_found；④诉讼关键词命中 → fail；⑤cash_coverage 由财务数字计算（mock financials）；⑥reject 优先于 insufficient 的 verdict 合成。
- [ ] Step 2: 实现 `fact_checks.py`（三检查器 + verdict 合成纯函数，检索失败吞掉按 not_found）。
- [ ] Step 3: Run `pytest tests/test_fact_checks.py -v` → PASS。
- [ ] Step 4: 接线 `judge.py` + `seeds.py` 改写；`tests/test_screener_judge.py` 补一条「fact_check fail → reject 且 LLM 未被调用该标准」用例。
- [ ] Step 5: Run `pytest tests/test_screener_judge.py tests/test_screener_judge_eval.py tests/test_screener_presets_models.py -v` → PASS。
- [ ] Step 6: Commit `feat: 事实检查确定性化，LLM仅判叙事标准`.

### Task 9: 报告改造为投资理由文档 + latest-report 指针

**Files:**
- Modify: `backend/screener/report.py` — 推荐股分区改为四段固定结构（量化筛选带数值与行业分位 → 事实检查（来自 criteria_hits 中 fact_check 项）→ 年报证据（LLM 叙事标准命中）→ 不推荐/存疑原因）；概览保留数据时效与股票池卫生；删除近似命中残留（Task 6 已清）
- Modify: `backend/screener/routes/runs.py` — 新增 `GET /screener/latest-report`（最近 completed run 的 markdown 文本；无则 404）
- Modify tests: `tests/test_screener_report.py` 断言四段标题存在且顺序正确；`tests/test_screener_api.py` 新增 latest-report 用例（无 completed run → 404；有 → 200 文本）

**Interfaces:**
- Consumes: `ScreenerJudgement.criteria_hits` 中 fact_check 结构（Task 8）；现有 `_fmt_money/_fmt_price`。
- Produces: `GET /api/v1/screener/latest-report` → `{"run_id": str, "report": str}`。

- [ ] Step 1: 写 report 四段结构失败测试 → FAIL。
- [ ] Step 2: 改 `report.py`；新增 latest-report 路由。
- [ ] Step 3: Run `pytest tests/test_screener_report.py tests/test_screener_report_presets.py tests/test_screener_api.py -v` → PASS。
- [ ] Step 4: Commit `feat: 报告改为投资理由文档，新增latest-report指针`.

### Task 10: 前端收缩

**Files:**
- Delete: `frontend/src/views/Knowledge.vue`, `frontend/src/components/ReportCharts.vue`, `frontend/src/components/PresetManager.vue`
- Modify: `frontend/src/router/index.ts`（删 knowledge 路由）, `frontend/src/components/Sidebar.vue`（删菜单项）, `frontend/src/stores/api.ts`（删组合/表现/取消/CSV/预设写/knowledge hooks，新增 `useScreenerLatestReport` GET hook）, `frontend/src/views/Screener.vue`（收缩：顶部触发条（预设多选+pool+combine）→ 数据质量卡 → 运行状态 → 报告主体（latest-report 直载 + 运行列表点选）；目标 ~400 行）, `frontend/src/views/CompanyDetail.vue` / `Market.vue`（如引用被删 hooks 一并清理）
- Modify: `frontend/src/views/System.vue` 如引用被删 hooks 清理

- [ ] Step 1: 删文件与引用；Screener.vue 按上述结构重写（沿用现有 marked+DOMPurify 渲染）。
- [ ] Step 2: Run `cd frontend && npm run build` → vue-tsc 零错误（typecheck 闸）。
- [ ] Step 3: `grep -rn "Knowledge\|PresetManager\|ReportCharts\|useCancelScreenerRun\|useRebalance" frontend/src` → 零命中。
- [ ] Step 4: Commit `chore: 前端收缩为价值推荐清单视图`.

### Task 11: 文档同步与全量验证

**Files:**
- Modify: `README.md`（模块表删组合/表现/回测UI行，核心链路改为清单交付）, `USAGE.md`, `backend/README.md`, `memory/ai-research-os-session.md`（追加变更日志条目）
- Modify: `backend/tools/README.md`（修 archive 引用失配）

- [ ] Step 1: 文档更新（中文，保持各文件既有风格）。
- [ ] Step 2: 全量验证：`cd backend && .venv\Scripts\python -m pytest -v` 全绿；`cd frontend && npm run build` 绿；改动文件 `ruff check` + `pre-commit run --files <changed>` 通过。
- [ ] Step 3: Commit `docs: 同步二次瘦身文档`.
