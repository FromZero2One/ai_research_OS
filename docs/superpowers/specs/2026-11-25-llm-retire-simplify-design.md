# 三次简化 · 深判退役设计文档

> 日期：2026-11-25。用户已批准四项决策（LLM 深判整体退役 / diff+notify 全删 / 回测纯 JSON/CSV / 一次做完）。
> 前置：二次瘦身已完成（1100d32）。本轮是「多产品平台 → 每日策略清单」的最后一步减法。

## Intent（为什么）

核心诉求 = 按策略（内置 8 套，后续增加）筛出股票，产出清单。判断已前置为确定性规则（量化规则 + fact_checks 三检查器），LLM 深判只剩 14 条低区分度叙事标准，是系统里最重（~40KB）、最慢（单轮 10min）、bug 密度最高的环节。本轮把它和其余「平台时代器官」全部退役，让运行链路零 LLM 依赖（知识库问答除外）。

## Goals / Non-goals / Anti-goals

- **Goals**：单轮运行 ≤2 分钟；screener 模块缩至 ~15 文件；运行链路无 LLM 调用；diff/notify/回测 service 层删除；tools 归档。
- **Non-goals**：不做新功能（分位数估值、券商口径修复、策略分层标注是**优化项**，另立项，不混入本轮）。
- **Anti-goals**：不删 `ScreenerJudgement` 表与历史运行数据（表保留，ORM 类保留——历史清单还要展示）；不删知识库问答（document/knowledge 模块不动）；不删 `POST /runs` 深判结果的**历史读取端点**（旧 run 的 judgements 仍可查）。

## 关键决策（用户拍板）

1. **LLM 深判整体退役**：不保留摘要生成。推荐股的「投资理由」= 量化命中明细（数值+行业分位）+ fact_checks 结果。
2. **diff + notify 全删**：含调度钩子、Webhook 配置项。
3. **回测纯 JSON/CSV**：脚本直调 `backtest.py` 纯函数，落 CSV/JSON 文件；删 `backtest_service.py`（状态机+任务队列）、`backtest_report.py`、`screener_backtest` 任务 handler、调度钩子。
4. **一次做完**：单分支连续 dispatch，最后整分支评审。

## 改动清单（builder 执行依据）

### A. LLM 深判退役（最大项）

- **删文件**：`screener/judge.py`、`screener/judge_eval.py`、`screener/eval/`（含 judge_cases.jsonl）、`scripts/eval_judge.py`（若存在）、`core/llm_usage.py`（先 grep 确认知识库问答未用；若共用则保留该文件仅删 screener 引用）。
- **改 `screener/service.py`**：`run_screener` 删除 judging 阶段——初筛+fact_checks 完成后直接生成报告并 completed；run 状态机 `judging` 阶段移除（新运行不再经过；历史行含 judging 的展示不受影响，状态映射保留）；`ScreenerJudgement` 写入逻辑删除；qualitative 叙事标准不再进入任何执行路径（compose 仍输出该键可保留，仅作展示）。
- **改 `screener/report.py`**：推荐股分区从四段改三段——量化筛选 → 事实检查 → **不推荐/存疑原因**；删「年报证据」段（:248-260）；「存疑/不推荐原因」来源改为 fact_checks not_found 项 + `excluded_missing` 缺数据项（build_report 已收该参数 :121/:551），report.py 需实质性改写而非简单删段。
- **顺带清理（勘察确认）**：`core/llm_usage.py` 删除 + `core/system_routes.py` 的 `get_llm_usage` 端点一并删（该文件仅此一个端点，倾向整个 system_routes 删除 + `api/app.py:57,257` 注册清理）；`service.py:139-156` `_auto_pass_judgement` 可改造为无 LLM 的确定性判定生成器（量化命中+fact_checks 落 `ScreenerJudgement`，保住前端历史明细表格不空）；`service.py` 顶部 `create_llm`/`_create_knowledge` 删除；`SCREENER_JUDGE_CONCURRENCY`/`SCREENER_MIN_CONFIDENCE` 配置项（config.py:102-103）清理。
- **改 `screener/fact_checks.py`**：`apply_fact_check_verdict` 中 LLM 结论分支移除——fail → reject，not_found → insufficient，pass → 通过；不再有 LLM 结果合并。
- **改 `core/screener_schedule.py` / `core/scheduler.py`**：调度与超时逻辑中 judging 相关等待/状态清理。
- **models**：`ScreenerJudgement` ORM 类**保留**（历史数据展示），`verdict` 枚举保留。
- **测试**：删 `test_screener_judge*.py`、`test_screener_judge_eval.py`、fact_checks 中 LLM 合并用例改写；`test_screener_api.py` 全链路 mock 改为无 LLM（不再需要 LLM mock 桩）；补一条「qual=0 预设运行不触发任何 LLM 调用」断言。

### B. diff + notify 全删

- 删：`screener/diff.py`、`screener/diff_service.py`、`screener/notify.py`、`routes/runs.py` 的 `GET /runs/{id}/diff` 路由、`core/screener_schedule.py` 中 diff 生成与 webhook 推送调用（含 :22-23/:56-99 diff 逻辑、:143-157 超时告警 webhook）、`service.py:582-600` 失败告警 webhook、`SCREENER_WEBHOOK_*` 四项配置（config.py:110-114）、`screener.diff` 事件写入。
- 测试：删 `test_screener_diff.py`、notify 相关用例。

### C. 回测去框架化

- 删：`screener/backtest_service.py`、`screener/backtest_report.py`；handler 注册在 `backtest_service.py:518-525`（随文件消失，`api/app.py:94` 的 import 副作用一并删）；`fail_stale_backtest_runs` :462。core/scheduler 无 backtest 钩子（勘察确认）。
- **保留**：`screener/backtest.py`、`screener/backtest_data.py`、`tools/run_backtest_queue.py`。
- **改 `tools/run_backtest_queue.py`**：直调 `backtest.py` 纯函数 + `backtest_data.py` 拉数（现调用的 `/backtests` 端点已不存在，此改动即修复断链），结果写 `screener/reports/backtest-{preset}-{date}.json`（summary+yearly+holdings 字段原样 dump）；不再创建 task/run 行。
- 测试：删 `test_screener_backtest_api.py`、`test_screener_backtest_models.py` 中 service/状态机用例；`test_screener_backtest_pit.py:10` import 的 `backtest_service._load_financials_by_period` 迁移到 `backtest_data.py` 或改从该处取数；保留 `backtest.py`/`backtest_data.py` 纯函数测试（含 PIT）。

### D. 死端点与 tools 归档

- 删 `screener/actions.py`（watchlist 已无消费方）及对应路由；删 `GET /runs/{id}/export` CSV 导出（前端无入口，文档已改口径）；删逐只 judgement 明细端点中对新运行的无意义分支（历史 run 仍可查则保留读取）。
- tools 归档（移入 `backend/tools/archive/`，不删除）：`check_pg_activity.py`、`check_tasks.py`、`check_coverage.py`、`check_universe.py`、`check_period_completeness.py`、`check_pending_docs.py`、`confidence_dist.py`、`doc_task_status.py`、`final_report.py`、`ingest_recommended.py`、`recent_activity.py`、`show_holdings.py`、`show_judgement.py`、`screener_task_status.py`、`kb_status.py`（勘察确认：候选间无互相 import；`_db.py` 被 8 个保留脚本共用**必须留原地**，归档脚本复制一份 `_db.py` 进 archive/）。
- `backend/tools/README.md` 同步归档清单。

### E. 文档与状态

- `README.md`/`USAGE.md`/`backend/README.md`/`frontend/README.md`：核心链路描述改为「初筛 → 事实检查 → 报告」三段，无 LLM；删 diff/webhook/回测报告章节；运行时长预期更新。
- `memory/ai-research-os-session.md`：追加变更日志条目。

## Constraints

- 不做 alembic 迁移、不 drop 表；ORM 类只删与运行链路绑定的（本轮预期不删任何模型类）。
- ruff 只跑改动文件；禁止全仓 format。
- 后端测试从 `backend/` 用 `.venv\Scripts\python -m pytest`；docker Postgres+Qdrant 须在跑。
- **零新增 LLM/akshare 真实调用**；全量测试后除既有失败清单外必须全绿。
- 既有失败（豁免）：`test_announcement_date_filters_future_data`、`test_presets_union_with_financials`、`test_snippet_hit_with_citation_kept`、document/knowledge 4 个 Ollama 环境失败、`test_skips_when_metric_present`。
- 提交信息 conventional commits，straight to main，不 push；每个提交先过目控制者。
- 提交切分建议：A 一个提交（`feat:` 或 `refactor:` 深判退役）、B 一个（`chore:` 删变化日报）、C 一个（`chore:` 回测去框架化）、D+E 一个（`chore:` 死端点清理与 tools 归档）。

## 留给 builder 的裁量

- `core/llm_usage.py` 去留以 grep 结果为准（知识库问答若在用则保留文件）。
- `ScreenerRun` 状态机：`judging` 值从新运行的流转中移除但 CHECK/枚举保留（历史行兼容），具体以测试全绿为准。
- 归档脚本逐个 import 检查的顺序与 `_db.py` 处置。
- 测试删改的粒度（保持「每个删除对象至少有一个 grep 清零验证」的计划惯例）。

## 验收标准

1. `grep -rn "judge\|diff\|notify\|webhook" backend/screener backend/core backend/api` → 除历史状态枚举/注释外零引用。
2. 全量 pytest：除豁免清单外全绿，且**总数显著减少**（预期 -60+ 用例）。
3. `npm run build` 绿；`grep -rn "diff\|backtest" frontend/src` → 零引用（本就无入口）。
4. 手动冒烟：本地起后端跑一次核心资产预设 run，单轮 ≤2 分钟，报告三段结构正常，`GET /latest-report` 200。
5. 整分支评审（MERGE_BASE=1100d32）通过。
