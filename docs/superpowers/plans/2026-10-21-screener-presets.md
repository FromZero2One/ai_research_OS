# Screener 预设标准库（v1.5）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把选股标准升级为可组合的预设库：指标入库、预设可编辑、触发时多选预设 + 组合方式（union/intersection/flatten），预设模式跳过 LLM 翻译。

**Architecture:** 新增两张表（`screener.metric_defs`、`screener.criteria_presets`）+ `ScreenerRun` 加 4 列；新增 `screener/presets.py`（CRUD + 组装规则，纯函数组装不走 LLM）；`service.trigger_run/run_screener` 分支 presets 模式；routes 加 4 个端点；前端 `Screener.vue` 触发区改造 + 预设管理。

**Tech Stack:** FastAPI + SQLAlchemy(async) + Alembic + pytest；Vue3 + TS + Element Plus（沿用现有页面风格）。

**Spec:** `docs/superpowers/specs/2026-10-21-screener-presets-design.md`（数据模型、组合语义、内置五套预设内容以此为准）

## Global Constraints

- 后端工作目录 `backend/`，测试命令 `python -m pytest`（PowerShell，无 `&&`）
- 改数据库必须走 alembic 迁移（不能用 create_all）
- 内置预设（is_builtin=True）不可 PUT/DELETE，PUT 内置返回 409
- 预设模式零 LLM 调用（组装是纯函数）
- quant_rules 元素复用 `rules_schema.py` 的形状：`{metric, op, value, missing_data_policy}`
- 中文文案；git 提交信息 conventional commits

## Review Focus

- 内置预设被 PUT/DELETE → 必须拒绝（测试钉住：test_update_builtin_rejected）
- preset_ids 引用不存在的预设 → 触发应 422 而非静默跑空（test_trigger_unknown_preset）
- union 模式同一只票同时命中多预设 → hits 去重且计数正确（test_union_multi_hit）
- flatten 模式缺数据策略冲突（同一 metric 两个预设策略不同）→ 后者覆盖前者，确定性排序（test_flatten_conflict_deterministic）
- v1 旧 run（mode 为 NULL）详情接口不受影响（test_v1_run_compat）

---

### Task 1: 模型 + 迁移 + 种子数据

**Files:**
- Modify: `backend/screener/models.py`（加 `MetricDef`、`CriteriaPreset`；`ScreenerRun` 加 `mode`/`pool_override`/`preset_ids`/`combine_mode` 列，nullable，mode 默认 NULL 表示 v1 自由文本）
- Create: `backend/alembic/versions/c8e1b7d4f2a9_add_metric_defs_and_presets.py`
- Test: `backend/tests/test_screener_presets_models.py`

**Interfaces:**
- Produces: `MetricDef(key, name_cn, category, data_source, description)`、`CriteriaPreset(name, description, style_tag, quant_rules JSONB, qualitative JSONB, suggested_pool, is_builtin, is_active)` ORM 模型；`ScreenerRun.preset_ids: list | None`、`combine_mode: str | None`、`pool_override: str | None`、`mode: str | None`

- [ ] **Step 1: 失败测试** — 断言：两表可插入查询；`CriteriaPreset.quant_rules` 默认 `[]`；内置五套预设种子存在（key/style 断言：core/growth/value/garp/cycle）；`metric_defs` 种子至少包含 roe/net_margin/gross_margin/debt_to_equity/current_ratio/operating_cash_flow/revenue/net_income/market_cap/turnover，且 data_source 正确（snapshot 类指标 → snapshot）
- [ ] **Step 2: 跑测试确认失败**（ImportError/表不存在）
- [ ] **Step 3: 实现** — 模型 + 迁移（down_revision=`b5d2f8a3c6e1`）。种子数据写进迁移的 `upgrade()`（metric_defs 约 15 条、内置 5 套预设内容照 spec 的"内置五套预设"一节逐字落地）
- [ ] **Step 4:** `alembic upgrade head` 后测试通过
- [ ] **Step 5: Commit** `feat(screener): metric_defs + criteria_presets models, migration, builtin seeds`

### Task 2: 预设 CRUD 服务

**Files:**
- Create: `backend/screener/presets.py`
- Test: `backend/tests/test_screener_presets_service.py`

**Interfaces:**
- Consumes: Task 1 模型
- Produces: `list_presets(db, include_inactive=False) -> list[CriteriaPreset]`；`create_preset(db, data: dict) -> CriteriaPreset`（校验 quant_rules 非空、metric 已在 metric_defs、op ∈ {>,<,>=,<=,==}）；`update_preset(db, preset_id, data) -> CriteriaPreset | None`（内置 → raise `BuiltinPresetError`）；`delete_preset(db, preset_id) -> bool`（内置 → raise `BuiltinPresetError`）；`list_metrics(db) -> list[MetricDef]`（按 category, key 排序）

- [ ] **Step 1: 失败测试** — create 正常/坏 op 拒绝/未知 metric 拒绝；update 内置 raise、update 自建 OK；delete 内置 raise、自建 OK 后 list 不再含；list_metrics 分组排序
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（纯 async SQLAlchemy，校验失败 raise ValueError）
- [ ] **Step 4: 测试通过**
- [ ] **Step 5: Commit** `feat(screener): preset CRUD service with builtin protection`

### Task 3: 组装规则（纯函数，union/intersection/flatten）

**Files:**
- Create: `backend/screener/compose.py`
- Test: `backend/tests/test_screener_compose.py`

**Interfaces:**
- Consumes: `CriteriaPreset.quant_rules/qualitative/suggested_pool`
- Produces: `compose_rules(presets: list[CriteriaPreset], pool: str, combine: str) -> dict` — 返回与 v1 rules 同形状的 dict（`stock_pool`/`quant_rules`/`qualitative_criteria`/`candidate_limit`），另加 `combine: combine`、`preset_names: [str]`；`evaluate_quant_rules_by_preset(pool, presets, financials) -> dict[str, dict]` — 每个预设独立跑初筛，返回 `{ticker: {"hits": int, "presets": [name...], "score": float}}`（union 用）

- [ ] **Step 1: 失败测试** — flatten：两预设 quant_rules 拼接 AND、同 metric 冲突时按预设传入顺序后者覆盖（传入列表顺序即确定性）；intersection：`quant_rules` 拼接 + `combine="intersection"`；union：qualitative 去重拼接（保持顺序）、`combine="union"`；pool 参数覆盖 preset 的 suggested_pool；`evaluate_quant_rules_by_preset`：mock 3 只票 2 套预设 → hits 计数、presets 名单、去重
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（复用 `screening.evaluate_quant_rules` 做单预设初筛）
- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(screener): compose rules from presets (union/intersection/flatten)`

### Task 4: service 接入 presets 模式

**Files:**
- Modify: `backend/screener/service.py`（`trigger_run` 加 `params: dict | None = None`；`run_screener` 在 `run.mode == "presets"` 时跳过 translate，用 Task 3 组装；union 模式用 `evaluate_quant_rules_by_preset` 排名取前 candidate_limit）
- Modify: `backend/screener/models.py` 的 `ScreenerRun`（如 Task 1 已加列则只改 service）
- Test: `backend/tests/test_screener_presets_run.py`

**Interfaces:**
- Consumes: Task 2 CRUD、Task 3 compose
- Produces: `trigger_run(db, params: dict | None = None) -> ScreenerRun | None`，params 形如 `{"mode": "presets", "pool": "all", "preset_ids": [uuid...], "combine": "union"}`；params 为 None 时行为与 v1 完全一致（自由文本）

- [ ] **Step 1: 失败测试** — presets 模式端到端（mock spot fetch + LLM judge，沿用 `test_screener_api.py` 现有 mock 手法）：run.mode/preset_ids/combine 落库；translate 未被调用（断言 `ScreenerRule` 无新行）；union 模式报告里候选带 hits；旧路径（params=None）回归不变；preset_ids 含不存在 id → raise ValueError（路由层转 422）
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 通过**（连同 `tests/test_screener_api.py` 全量回归该模块）
- [ ] **Step 5: Commit** `feat(screener): presets-mode run pipeline without LLM translation`

### Task 5: 路由

**Files:**
- Modify: `backend/screener/routes.py`（加 `GET /metrics`、`GET|POST /presets`、`PUT|DELETE /presets/{id}`；`POST /runs` 加可选 body → 传给 trigger_run）
- Test: `backend/tests/test_screener_presets_api.py`

**Interfaces:**
- Consumes: Task 2/4
- Produces: HTTP 端点，见 spec API 一节；POST /runs body 校验失败 → 422；PUT 内置预设 → 409

- [ ] **Step 1: 失败测试**（httpx AsyncClient，沿用现有 test_screener_api 的 fixture）
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（`BuiltinPresetError` → 409；ValueError → 422）
- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(screener): presets & metrics API endpoints`

### Task 6: 前端

**Files:**
- Modify: `frontend/src/views/Screener.vue`（触发区分模式：预设组合=股票池下拉+预设多选卡片+组合方式单选；自由文本=现有编辑器）
- Create: `frontend/src/components/PresetManager.vue`（预设卡片列表 + 新建/编辑抽屉：量化规则行编辑——指标下拉按 category 分组、操作符、阈值、缺数据策略；定性条目列表）
- Test: 无组件测试框架 — 用 `npx vue-tsc --noEmit` + 手动验证兜底

**Interfaces:**
- Consumes: Task 5 端点

- [ ] **Step 1: 实现**（沿用页面现有 api 调用与样式模式）
- [ ] **Step 2:** `npx vue-tsc --noEmit` 0 错误
- [ ] **Step 3:** 手动验证：新建预设→触发 union 跑一轮→报告显示命中预设
- [ ] **Step 4: Commit** `feat(screener-ui): preset selection trigger + preset manager`

### Task 7: 报告增强 + 收尾

**Files:**
- Modify: `backend/screener/report.py`（union/intersection 模式：推荐表加"命中预设"列，吻合度说明按预设分组）
- Test: `backend/tests/test_screener_report.py` 加 2 个用例

- [ ] **Step 1: 失败测试** — 报告含预设名标注；mode=None（v1）报告不变
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 通过 + 全模块回归**
- [ ] **Step 5: Commit** `feat(screener): report annotates matched presets`
