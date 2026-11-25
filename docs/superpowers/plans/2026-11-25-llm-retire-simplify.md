# 深判退役 · 三次简化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 运行链路零 LLM——删 LLM 深判、变化日报+Webhook、回测 service 框架、死端点，归档 15 个 tools 脚本，单轮运行 ≤2 分钟。

**Architecture:** 纯减法。run_screener 从四步缩为「compose → 确定性初筛+fact_checks → 报告三段」；`_auto_pass_judgement` 改造为确定性判定生成器保住历史明细链路；报告「存疑/不推荐原因」改由 fact_checks not_found + excluded_missing 驱动。

**Tech Stack:** FastAPI + SQLAlchemy async + pytest（asyncio auto）。

**Spec:** `docs/superpowers/specs/2026-11-25-llm-retire-simplify-design.md`（勘察修正已并入，本计划以其为准）

## Global Constraints

- 不做 alembic 迁移、不 drop 表；ORM 类本轮一个都不删（`ScreenerJudgement` 保留，历史数据可查）。
- ruff 只跑改动文件；禁止全仓 format。
- 后端命令从 `backend/` 用 `.venv\Scripts\python -m pytest`；docker Postgres(:5432)+Qdrant(:6333) 必须在跑（`docker compose -f docker/docker-compose.yml up -d`）。
- 零新增 LLM/akshare 真实调用。
- 提交信息 conventional commits（AGENTS.md 风格），straight to main，不 push；**每个提交信息先交控制者过目，不自行 commit**——工作做到测试全绿为止。
- 既有测试失败（豁免，勿修勿归咎）：`test_announcement_date_filters_future_data`、`test_presets_union_with_financials`、`test_snippet_hit_with_citation_kept`、document/knowledge 4 个 Ollama 环境失败（`test_upload_markdown`/`test_upload_txt`/`test_search_after_document_upload`/`test_search_with_doc_type_filter`）、`test_skips_when_metric_present`。

## Review Focus

- 删 judge 后「存疑/不推荐原因」必须有真实来源（fact not_found + excluded_missing），不能出现空段——Task 1 测试断言 reasons 非空场景。
- 历史运行（旧 judging 时代的 run）明细读取不 500——`GET /runs/{id}` 对含 judgements 的历史行仍 200——Task 1 测试钉死。
- 删 webhook 后调度失败路径不得抛未捕获异常——Task 2 grep + 调度测试。
- 回测脚本直调后 PIT 语义不变（公告日过滤）——Task 3 PIT 测试保留通过。
- `GET /runs/{id}/export` 与 `/watchlist` 删除后前端 grep 零命中——Task 4 验证步。

---

### Task 1: LLM 深判退役（最大项）

**Files:**
- Delete: `backend/screener/judge.py`, `backend/screener/judge_eval.py`, `backend/screener/eval/`（整目录含 judge_cases.jsonl）, `backend/core/llm_usage.py`, `backend/core/system_routes.py`, `backend/scripts/eval_judge.py`（若存在）
- Modify: `backend/screener/service.py` — 删 :16 `create_llm` import、:22 `from screener.judge import judge_candidates`、:89 `_create_knowledge`、:389 `llm = create_llm()`、:502-504 judging 状态提交（初筛后直接 completed 前置的报告阶段，不再经过 judging 状态；`ACTIVE_STATUSES`/`:77` 保留 `judging` 枚举值以兼容历史行查询）、:506-544 judge_candidates 调用块、:585-600 notify 失败告警（属 Task 2 范围则此任务只删 judge 部分，notify 留给 Task 2——以不重复为准：judge 相关本任务删，webhook 相关 Task 2 删）；**改造 :139-156 `_auto_pass_judgement(candidate) -> dict`** 为确定性判定生成器：输入候选+fact_checks 结果，输出 `ScreenerJudgement` 落库行（verdict: fact fail→reject / not_found→insufficient / 其余→recommend；criteria_hits 存量化命中明细+fact 条目；confidence 固定 1.0；reasons 留空列表），在原 :529 位置改为循环调用它逐只落库（保留原 :539 幂等 delete+insert 模式）
- Modify: `backend/screener/fact_checks.py` — `apply_fact_check_verdict` 移除 LLM 结论合并分支：fail→reject、not_found→insufficient、pass→recommend；不再接收/返回 LLM 结果
- Modify: `backend/screener/report.py` — 删「年报证据」段 :248-260；「不推荐/存疑原因」改写：reasons 来源 = fact_entries 中 `result=="not_found"` 项 + `excluded_missing` 缺数据项（build_report 已收该参数）；推荐股分区改三段固定结构（量化筛选 → 事实检查 → 不推荐/存疑原因），docstring/注释同步
- Modify: `backend/core/config.py` — 删 :102-103 `SCREENER_MIN_CONFIDENCE`、`SCREENER_JUDGE_CONCURRENCY`
- Modify: `backend/api/app.py` — 删 :53 system_routes import + router 注册、`create_llm` 相关（grep 定位）；`core/scheduler.py` 中 judging 相关若引用则清理
- Delete tests: `backend/tests/test_screener_judge.py`, `backend/tests/test_screener_judge_eval.py`
- Modify tests: `backend/tests/test_fact_checks.py` — LLM 合并用例改写为纯三态断言；`backend/tests/test_screener_api.py` — 全链路用例删 LLM mock 桩（运行不再需要），新增：①qual=0 预设运行全程零 LLM 调用（无桩可打即 grep service.py 无 `create_llm`）；②「fact fail → verdict=reject 且 judgements 落库」；③历史 run（手工造一条 status=completed + judgements 行）`GET /runs/{id}` 仍 200 且含 judgements；④报告三段标题存在且顺序正确（更新既有四段测试）；⑤不推荐/存疑段在 not_found 场景非空
- Modify: `backend/tests/test_core.py` / 其他引用 `system_routes`、`/ai/usage` 的测试——grep 后删对应用例

**Interfaces:**
- Produces: `run_screener` 完成后 run.status 直接 screening→completed；`ScreenerJudgement` 行由 `_auto_pass_judgement` 改造版生成（函数名可保留，签名扩展为 `(candidate: dict, fact_results: list[dict]) -> dict`）；报告三段结构。
- 前端无需改（`detailData?.judgements` 表格继续有数据；本轮不碰前端）。

- [ ] Step 1: 先改测试（上述 Modify tests 五条）→ 运行确认 FAIL
- [ ] Step 2: 删文件 + service/fact_checks/report/config/app 改造
- [ ] Step 3: `grep -rn "judge_candidates\|judge_eval\|llm_usage\|system_routes\|create_llm" backend/` → 零命中（报告三段 docstring 除外）
- [ ] Step 4: Run `pytest tests/test_fact_checks.py tests/test_screener_api.py tests/test_screener_report.py tests/test_screener_report_presets.py tests/test_core.py -v` → PASS（豁免清单除外）
- [ ] Step 5: 拟提交信息交控制者过目后 commit `feat: 深判退役，运行链路零LLM`

### Task 2: 变化日报 + Webhook 全删

**Files:**
- Delete: `backend/screener/diff.py`, `backend/screener/diff_service.py`, `backend/screener/notify.py`
- Modify: `backend/core/screener_schedule.py` — 删 :22-23 import、:56-99 diff 生成+事件、:72-99 notify、:143-157 超时/失败告警 webhook（失败时仅 logger.error，不推送）；`:18 _ACTIVE` 保留
- Modify: `backend/screener/routes/runs.py` — 删 :366-388 `GET /runs/{run_id}/diff`
- Modify: `backend/core/config.py` — 删 :110-114 四个 `SCREENER_WEBHOOK_*`
- Delete tests: `backend/tests/test_screener_diff.py`、notify 相关用例（grep 定位）
- Modify tests: 调度测试（`test_core.py` 或 screener_schedule 相关）删 webhook/diff 断言，补「run 失败路径不抛异常且仅记日志」

**Interfaces:**
- Produces: `screener_schedule` job 只运行预设+落报告，无任何推送；`GET /schedule` 响应不含 webhook 字段（若有则删）。

- [ ] Step 1: 改测试（删 diff/webhook 断言、补失败路径纯日志用例）→ FAIL
- [ ] Step 2: 执行删除
- [ ] Step 3: `grep -rn "diff\|notify\|webhook\|WEBHOOK" backend/screener backend/core backend/api` → 零命中（无关词如 differential 除外）
- [ ] Step 4: Run `pytest tests/test_core.py tests/test_screener_api.py tests/test_screener_schedule*.py -v` → PASS
- [ ] Step 5: 拟提交信息交控制者后 commit `chore: 删除变化日报与Webhook推送`

### Task 3: 回测去框架化

**Files:**
- Delete: `backend/screener/backtest_service.py`, `backend/screener/backtest_report.py`
- Modify: `backend/api/app.py` — 删 :94 `import screener.backtest_service`
- Modify: `backend/tools/run_backtest_queue.py` — 直调 `backtest.py` 纯函数 + `backtest_data.py` 拉数；结果写 `screener/reports/backtest-{preset}-{YYYYMMDD}.json`（summary+yearly 原样 dump）；删除任务队列/`screener_backtest` handler 触发逻辑
- **迁移**: `backtest_service._load_financials_by_period`（含公告日 PIT 过滤逻辑）→ 移入 `backtest_data.py`（签名不变）
- Delete tests: `backend/tests/test_screener_backtest_api.py`, `backend/tests/test_screener_backtest_models.py` 中 service/状态机用例
- Modify tests: `backend/tests/test_screener_backtest_pit.py` — :10 import 改 `from screener.backtest_data import _load_financials_by_period`，用例主体不动（PIT 语义钉死）
- Modify: `backend/tests/test_screener_backtest_core.py`/`test_screener_backtest_data.py` — 若引用 backtest_service 则清理

**Interfaces:**
- Produces: `backtest_data._load_financials_by_period(...)`（签名与原 backtest_service 版一致）；`tools/run_backtest_queue.py` 零 DB 任务行写入。

- [ ] Step 1: 迁移 `_load_financials_by_period` 到 backtest_data.py；改 PIT 测试 import → Run `pytest tests/test_screener_backtest_pit.py -v` → PASS
- [ ] Step 2: 删 service/report 文件与 app.py import；删对应测试
- [ ] Step 3: 改 `run_backtest_queue.py` 直调 + JSON 落盘；`grep -rn "backtest_service\|backtest_report\|screener_backtest" backend/` → 零命中
- [ ] Step 4: Run `pytest tests/test_screener_backtest_core.py tests/test_screener_backtest_data.py tests/test_screener_backtest_pit.py -v` → PASS
- [ ] Step 5: 拟提交信息交控制者后 commit `chore: 回测去框架化，脚本直调纯函数`

### Task 4: 死端点清理 + tools 归档 + 文档

**Files:**
- Delete: `backend/screener/actions.py`
- Modify: `backend/screener/routes/runs.py` — 删 :241-286 `GET /runs/{run_id}/export`、:389- `POST /runs/{run_id}/watchlist`；judgements 读取端点保留
- Modify: `backend/screener/routes/__init__.py` — 如有 actions router 注册则清
- Move to `backend/tools/archive/`（15 个，复制 `_db.py` 进 archive）: `check_pg_activity.py` `check_tasks.py` `check_coverage.py` `check_universe.py` `check_period_completeness.py` `check_pending_docs.py` `confidence_dist.py` `doc_task_status.py` `final_report.py` `ingest_recommended.py` `recent_activity.py` `show_holdings.py` `show_judgement.py` `screener_task_status.py` `kb_status.py`
- Modify: `backend/tools/README.md` — 归档清单同步
- Modify docs: `README.md`（核心链路三段、无 LLM、无 CSV 按钮）、`USAGE.md`（同口径）、`backend/README.md`（模块表、API 清单、配置变量表删 WEBHOOK/JUDGE/MIN_CONF、报告三段）、`frontend/README.md`（如提 export/watchlist 则同步）、`memory/ai-research-os-session.md`（追加 2026-11-25 三次简化条目）
- Delete tests: `backend/tests/test_screener_api.py` 中 export/watchlist 用例

- [ ] Step 1: 删 actions.py + 两个路由 + 对应用例
- [ ] Step 2: tools 归档（git mv）+ 复制 `_db.py` + README 同步
- [ ] Step 3: `grep -rn "watchlist\|export_run\|/export" backend/screener frontend/src` → 零命中；`grep -rn "add_to_watchlist" backend/` → 零命中
- [ ] Step 4: Run `pytest tests/test_screener_api.py -v` → PASS
- [ ] Step 5: 文档更新（中文，保持既有风格）
- [ ] Step 6: 拟提交信息交控制者后 commit `chore: 清理死端点，归档历史排查脚本，同步文档`

### Task 5: 全量验证 + 冒烟

- [ ] Step 1: `cd backend && .venv\Scripts\python -m pytest -q`（预计 40 分钟）→ 除豁免清单外全绿，总数较上轮（392）显著减少
- [ ] Step 2: `cd frontend && npm run build` → 绿（前端本轮未改，验证无连带破坏）
- [ ] Step 3: 改动后端文件 ruff check（只跑改动文件）
- [ ] Step 4: 手动冒烟（docker + backend 起来后）：`POST /api/v1/screener/runs`（核心资产预设）→ 轮询至 completed → 断言耗时 ≤2 分钟、`GET /latest-report` 200 且报告三段、`GET /runs/{id}` 含 judgements（确定性生成）
- [ ] Step 5: 冒烟结果记入汇报；如失败修复后重跑

### Task 6: 最终整分支评审

- [ ] 派评审员审 `git diff 1100d32..HEAD` 全量 diff：验收标准对照 spec（grep 清零、零 LLM 链路、历史兼容、文档一致）→ 通过后 finishing-a-development-branch
