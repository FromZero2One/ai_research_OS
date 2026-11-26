# 五次简化实施计划（死重清除 + 分析质量修复）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删掉无消费方的 LLM 问答/company/news/BacktestRun 死重，修复券商 cash_coverage 误判，给报告补轮次对比、去恒定 confidence、加预设证据分层。

**Architecture:** 工程线纯删除（检索路径保留，LLM 链整体退役）；分析线在 fact_checks/report/seeds 三个纯函数文件上做小步修改，全部可单测。

**Tech Stack:** Python 3.13 + FastAPI + SQLAlchemy async；Vue 3.5 + vue-tsc。

**Spec:** `docs/superpowers/specs/2026-11-26-deadweight-clear-analysis-quality-design.md`

## Global Constraints

- 不 drop 表、不做删列迁移（删类留表）
- ruff 只跑改动文件：`cd backend && .venv\Scripts\python -m ruff check <files>`
- pytest 从 `backend/`：`.venv\Scripts\python -m pytest -v`；与冒烟严格串行
- 提交信息先过目控制者，不自行 push
- 前端改动后 `cd frontend && npm run build`（vue-tsc 闸）必须绿

## Review Focus

1. 删 LLM 后 fact_checks 的 KB 检索必须仍工作——audit_opinion/litigation 依赖 `knowledge_service` 检索方法，误删即断粮（Task E1 步骤 6 回归覆盖）
2. company 退役时 `screener/pool.py` 若读 `Company.is_active` 过滤股票池，误删 models 会断筛选链（Task E2 步骤 1 勘察覆盖）
3. exempt 状态若被 `_auto_pass_judgement` 的 not_found 优先级误吞，券商仍 insufficient（Task A1 测试断言 verdict=recommend 覆盖）
4. `prev_run` 查找若不排除当前 run 本身，对比段恒为「无变化」（Task A2 测试覆盖）
5. `SCREENER_SCHEDULE_PRESETS` 默认值改动后，`GET /screener/schedule` 与定时任务用例需同步（Task A4 步骤 4 覆盖）

---

### Task E1: knowledge LLM 问答退役

**Files:**
- Modify: `backend/knowledge/routes.py`（删 2 端点）
- Modify: `backend/knowledge/service.py`（删 `ask` 及其私有 prompt 方法，保留检索）
- Delete: `backend/core/llm_usage.py`、`backend/core/adapters/llm.py`
- Modify: `backend/core/config.py`（删仅问答消费的 LLM 配置项）、`backend/core/adapters/__init__.py`（如有导出）
- Test: 删 `backend/tests/` 中 ask/llm 用例

**Interfaces:**
- Produces: `KnowledgeService` 仅剩检索方法（`search`/`search_document`，签名不变）；fact_checks 与文档索引链不受影响

- [ ] **Step 1: 勘察 reranker 与 LLM 配置的消费面**

`git grep -n "reranker\|Reranker" -- backend` 确认 reranker 是否被检索链（非 ask）使用；`git grep -n "OPENAI_\|LLM_" -- backend/core/config.py backend/knowledge` 列出配置项消费方。结论写进提交信息正文（保留/删除依据）。

- [ ] **Step 2: 删 ask 链**

删 routes 的 `POST /ask`、`GET /llm/models`；删 `service.ask()` 及仅供它调用的私有方法；删 `core/llm_usage.py`、`core/adapters/llm.py` 及引用；config 删确认无消费方的配置项。检索端点与方法不动。

- [ ] **Step 3: 删测试 + 全量回归**

删 ask/llm_usage 相关用例。Run: `.venv\Scripts\python -m pytest tests/test_knowledge*.py -v` → PASS；随后全量（docker PG 已起）除豁免清单外全绿。

- [ ] **Step 4: ruff + 提交**

ruff 改动文件；提交信息过目：主题 `知识库问答退役，运行链路全系统零LLM`。

### Task E2: company 模块退役

**Files:**
- Delete: `frontend/src/views/Companies.vue`、`frontend/src/views/CompanyDetail.vue`
- Modify: `frontend/src/router/index.ts`（删 2 条路由）、`Sidebar.vue`、`components/StockSearch.vue`（改走 `/market/search`）
- Modify/Delete: `backend/company/routes.py`、`service.py`、`schemas.py`；`backend/api/app.py`（删注册）
- Modify: `backend/company/models.py` —— **仅当无下游引用时整删；若 screener/market 引用 Company 表则只留 models**

**Interfaces:**
- Produces: 前端路由 4 条（/screener /market /documents /system）；StockSearch 走 `/market/search`（api.ts 已有 `useMarketSearch`，签名不变）

- [ ] **Step 1: 勘察下游引用**

`git grep -n "from company\|company.models\|Company\b" -- backend/screener backend/market backend/core backend/document` 与 `git grep -n "useCompanies\|/companies" -- frontend/src`。Company 表被业务读 → 留 models.py；StockSearch 的消费点逐个列清。

- [ ] **Step 2: 前端删除与改道**

删 2 页面 + 路由 + Sidebar 项；StockSearch 切 `useMarketSearch`。Run: `npm run build` → 绿。

- [ ] **Step 3: 后端删除**

按 Step 1 结论删 routes/service/schemas（或仅 routes）；app.py 删注册；api.ts 删 company 段 hooks（若有残留调用一并清）。

- [ ] **Step 4: 测试 + 提交**

删 company 测试，全量回归除豁免外全绿。提交主题：`公司中心退役，股票搜索改走行情搜索`。

### Task E3: 零散死代码

**Files:**
- Delete: `backend/market/service/news_service.py`
- Modify: `backend/core/container.py`、`backend/core/interfaces.py`、`backend/market/service/__init__.py`（删 news 注册）
- Modify/Delete: `ScreenerBacktestRun` ORM 类（`backend/screener/models.py`）与读取端点（勘察 `git grep -n "backtest" -- backend/screener/routes`）
- Test: `backend/tests/test_akshare_safety.py` 中 news 相关用例

- [ ] **Step 1: 删 news_service 与 BacktestRun 残留**

删文件与注册；BacktestRun 读取端点存在则删，ORM 类删（表留）。

- [ ] **Step 2: 回归 + 提交**

全量 pytest；ruff。提交主题：`清理 news 服务与回测历史读取死代码`。

### Task A1: 券商 cash_coverage 豁免

**Files:**
- Modify: `backend/screener/fact_checks.py`（`_check_cash_coverage_sync` + `run_fact_checks` 签名）
- Modify: `backend/screener/seeds.py`（金融价值/深度价值的 cash_coverage 条目加 `exempt_financial_type`）
- Modify: `backend/screener/service.py`（调用点传 `financial_type`；`_auto_pass_judgement` 优先级合成）
- Modify: `backend/screener/report.py`（exempt 显示「不适用」）
- Test: `backend/tests/test_fact_checks.py`

**Interfaces:**
- Produces: `run_fact_checks(checks, knowledge, company_id, financials, financial_type=None) -> list[dict]`；fact result 新增 `"exempt"` 态：`{check, result: "exempt", detail: "不适用（券商口径）", hit: True, ...}`
- verdict 合成：fail → reject ＞ exempt/not_found → 不阻断 ＞ pass → recommend（exempt 不算 not_found，不得落 insufficient）

- [ ] **Step 1: 写失败测试**

```python
def test_cash_coverage_exempt_for_broker():
    check = {"check": "cash_coverage", "metric": "first_adequacy_ratio",
             "threshold": 10.0, "exempt_financial_type": ["other"]}
    res = run_fact_checks_sync_one(check, financials={}, financial_type="other")
    assert res["result"] == "exempt" and res["hit"] is True

def test_broker_not_insufficient():
    verdict = synthesize([_exempt_result()])   # _auto_pass_judgement 的合成逻辑
    assert verdict == "recommend"
```

- [ ] **Step 2: 跑测试确认失败** → `pytest tests/test_fact_checks.py -k exempt -v` FAIL
- [ ] **Step 3: 实现**：fact_checks 增 exempt 分支；seeds 金融价值条目加 `"exempt_financial_type": ["other"]`、深度价值条目加 `["bank", "insurance", "other"]`（金融股不适用工业现金比率）；service 传参与合成优先级调整
- [ ] **Step 4: 跑测试确认通过** → 全量 `test_fact_checks.py` + screener 相关 PASS
- [ ] **Step 5: 提交**：主题 `券商口径修复，现金覆盖检查增加豁免态`

### Task A2: 报告尾部轮次对比

**Files:**
- Modify: `backend/screener/report.py`（`build_report` 增参 + 尾部段落）
- Modify: `backend/screener/service.py`（查上一轮 completed run，传 `prev_recommendations`）
- Test: `backend/tests/test_screener_report.py`

**Interfaces:**
- Produces: `build_report(..., prev_recommendations: set[str] | None = None)`；报告尾部段：`较上一轮（YYYY-MM-DD）：新增 N 只（…）、移出 M 只（…）、连续推荐 K 只`；无上一轮时不输出该段

- [ ] **Step 1: 写失败测试**：有 prev → 段落含新增/移出/连续；prev=None → 无段落（断言文案不含「较上一轮」）
- [ ] **Step 2: 确认失败** → `pytest tests/test_screener_report.py -k prev -v` FAIL
- [ ] **Step 3: 实现**：service 查同 preset_ids 最近 completed（排除当前 run）取 judgements 的 ticker 集
- [ ] **Step 4: 确认通过** → report + service 用例 PASS
- [ ] **Step 5: 提交**：主题 `报告尾部增加轮次对比段`

### Task A3: 新判定不再写 confidence

**Files:**
- Modify: `backend/screener/service.py`（`_auto_pass_judgement` 删 confidence）
- Modify: `backend/screener/report.py`（推荐表删「置信度」列与 `_fmt_conf`）
- Modify: `backend/screener/routes/runs.py` schema（confidence 改可选，历史行仍透出）
- Test: `backend/tests/test_screener_report.py`、`test_screener_presets_run.py`

- [ ] **Step 1: 写失败测试**：新 judgement dict 无 `confidence` 键；报告推荐表头不含「置信度」
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**
- [ ] **Step 4: 确认通过**（历史 confidence 消费用例如有，改断言可选/None）
- [ ] **Step 5: 提交**：主题 `判定不再写恒定置信度字段`

### Task A4: 预设证据分层标注

**Files:**
- Modify: `backend/screener/seeds.py`（8 套预设加 `evidence: {grade, note}` 字段，数值按 spec）
- Modify: `backend/screener/report.py`（预设标题旁标注）
- Modify: `backend/core/config.py`（`SCREENER_SCHEDULE_PRESETS` 默认值 → 金融价值+深度价值）
- Modify: `backend/scripts/reseed_builtin_presets.py` 如需兼容新字段（幂等更新）
- Test: `backend/tests/test_screener_report.py`、`tests/test_core.py`（schedule 默认值）

**Interfaces:**
- Produces: 预设 dict 新增 `"evidence": {"grade": "verified|neutral|failed", "note": str}`；报告预设标题渲染 `[证据: verified] 5年超额 +11.45%，两段一致跑赢`

- [ ] **Step 1: 写失败测试**：金融价值 preset dict 含 `evidence.grade == "verified"`；GARP 为 `failed`；报告含「证据」标注
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**（seeds 数值照 spec 抄：金融价值/深度价值 verified，周期反转 neutral，高成长/核心资产/GARP failed；银行价值/保险价值按金融价值同 grade verified）
- [ ] **Step 4: 确认通过** + schedule 默认值用例 PASS
- [ ] **Step 5: 提交**：主题 `预设按回测证据分层，失效预设退出默认定时`

### Task F: 文档同步收尾

- [ ] **Step 1:** README/USAGE/backend README/`docs/ARCHITECTURE.md`/`memory/ai-research-os-session.md` 按最终口径同步（零 LLM、4 前端路由、exempt 态、证据分层、定时默认预设）
- [ ] **Step 2:** 全量 pytest + `npm run build` 最后一次全绿
- [ ] **Step 3:** 提交主题 `文档同步五次简化`；整分支评审（MERGE_BASE=四次简化完成后 HEAD）
