# 五次简化 · 死重清除 + 分析质量修复设计文档

> 日期：2026-11-26 立项。
> 前置：四次简化（基础设施退役）同日执行，HEAD 在其完成后基础上。
> 本轮两条线：**工程线**清掉无消费方的死重；**分析线**修复影响清单质量的真问题。

## Intent（为什么）

工程简化已到边际收益递减区，剩余可删项都是「无消费方」的死代码；而投研产出物（每日价值清单）的质量问题——券商被误判数据不足、8 套预设不分优劣平起平坐、报告无轮次连续性——是当前更值得投入的方向。本轮工程线收尾，分析线开工。

## 勘察结论（2026-11-26）

- `/knowledge/ask` 前端零消费：`stores/api.ts` 无 `/knowledge` 调用，Documents.vue 无问答 UI。全系统唯一 LLM 使用点是死重。
- fact_checks 只用 KB **检索**（`/knowledge/search` 路径），不用 LLM。
- 券商根因：`_attach_financial_types`（service.py:118）把非银非保险定为 `financial_type="other"`；金融价值预设 cash_coverage 要求 `first_adequacy_ratio`（券商无此指标）→ not_found → insufficient。
- **Redis 保留**：`screening.py:127` 快照缓存真实消费 `core/adapters/cache.py`（此前猜测有误）。
- `news_service`（2.9KB）：除 container/interfaces 注册外零消费。
- 回测历史行：脚本直调不落库，`screener_backtest_runs` 仅存历史行；报告已有 JSON/Markdown 落盘。

## 用户决策记录

- 2026-11-26：批准整轮立项（LLM 彻底退役选 A、company 退役、BacktestRun 历史读取删、券商口径修复、轮次对比、confidence 去除、预设证据分层）。valuation_history 喂数据与死表 drop 迁移为**待定项**，本轮不做。

## Goals / Non-goals / Anti-goals

- **Goals**：
  - 工程线：knowledge LLM 问答退役（保留检索）；company 模块退役；news_service 删除；BacktestRun 读取端点删除。
  - 分析线：券商 cash_coverage 豁免；报告尾部轮次对比；新判定不再写 confidence；报告/报告头预设证据分层标注。
- **Non-goals**：不动 market 采集链、document 上传索引链、Redis 缓存；不做估值分位数化（依赖 valuation_history 喂数据，另立项）；不 drop 任何表（延续「删类留表」）。
- **Anti-goals**：不丢 fact_checks 的检索能力（audit_opinion/litigation 依赖 KB search）；不丢运行历史可查性。

## 工程线

### Task E1：knowledge LLM 问答退役

**现状**：`backend/knowledge/routes.py` 有 4 端点：`POST /ask`、`GET /llm/models`、`GET /search`、`GET /search/document/{id}`。`ask()` 在 `knowledge/service.py:551`，依赖 `adapters/llm`、`llm_usage.py`。

**方案**：
1. 删 `POST /ask` 与 `GET /llm/models` 路由；删 `service.ask()` 方法及其 prompt 组装私有方法。
2. 删 `core/llm_usage.py`、`core/adapters/llm.py`、`core/adapters/reranker.py`（若仅 ask 链使用——勘察后自决，检索 hybrid 用它则保留）。
3. `config.py` 删 LLM 对话类配置（OPENAI_API_KEY 等仅问答消费的项；embedding 的 OLLAMA 配置保留）。
4. `knowledge/service.py` 收敛为纯检索服务；`GET /search` 两端点保留。
5. 文档口径更新：设计信条改为「全系统零 LLM」。
6. 测试：删 ask 相关用例；检索用例保持全绿。

### Task E2：company 模块退役

**现状**：`company/`（models/service/routes/schemas，~19KB）+ 前端 `Companies.vue`、`CompanyDetail.vue` 两条路由。股票池本体在 market/外部库，不在 company 表。研究中心已删，thesis/送入研究消费方已不存在。

**前置勘察**：grep `companies` 在 `stores/api.ts` 的调用点——StockSearch 组件若依赖公司搜索需改走 `/market/search`；`screener` 是否读 `company.companies` 的 `is_active`（pool 逻辑）需确认，若读则保留 models 只删路由与前端页。

**方案**：
1. 前端：删 `Companies.vue`、`CompanyDetail.vue` + 2 条路由 + Sidebar 项；`StockSearch` 改走 `/market/search`。
2. 后端：删 `company/routes.py` 与 app.py 注册；`models.py` 若被 screener/market 引用则保留（表不 drop），service/schemas/routes 删。
3. 测试：删 company 用例；全量回归。

### Task E3：零散死代码

1. 删 `market/service/news_service.py` + container/interfaces 注册 + `__init__.py` 导出。
2. 删 BacktestRun 读取端点（若存在路由）+ ORM 类引用；表保留。
3. `ScreenerBacktestRun` 模型类删除（表保留）。

## 分析线

### Task A1：券商 cash_coverage 豁免（真 bug，最高优先）

**方案**：`fact_checks.py` 的 cash_coverage 分支增加豁免：check 带 `"exempt_financial_type": ["other"]`（seeds.py 金融价值预设的条目加上）且候选 `financial_type` 命中列表时，返回 `{"result": "exempt", ...}`——合成 verdict 时 exempt 视同 pass（不适用，不是数据不足）。深度价值的 cash_ratio 检查对金融股同样豁免（金融股本不该用工业口径现金比率卡）。报告对 exempt 显示「不适用（券商口径）」。
**接口**：`run_fact_checks(checks, knowledge, company_id, financials)` → 增加 `financial_type: str | None` 参数（service.py 调用点传入候选的 financial_type）。

### Task A2：报告尾部轮次对比（最小核心）

**方案**：`report.py` 的 `build_report` 增加可选参数 `prev_run`（上一轮同口径 completed run 的推荐 ticker 集）。报告尾部一段：「较上一轮（{date}）：新增 N 只（列表）、移出 M 只（列表）、连续推荐 K 只」。上一轮查找逻辑 10 行内（同 preset_ids 的最近 completed run），不复活 diff_service。
**接口**：`build_report(..., prev_recommendations: set[str] | None = None)`；service.py 查上一轮后传入。

### Task A3：新判定不再写 confidence

**方案**：`_auto_pass_judgement` 不再写 `confidence` 字段（历史行保留）；`report.py` 推荐表删「置信度」列；API schema 若透出 confidence 改为可选。理由：恒定 1.0 无信息量，误导未来读者。

### Task A4：预设证据分层标注

**方案**：`seeds.py` 每套预设增加 `evidence` 元数据字段（静态，基于 2026-10-25 五年回测结论）：
- 金融价值/深度价值：`{"grade": "verified", "note": "5年超额 +11.45% / +10.16%，两段一致跑赢"}`
- 周期反转：`{"grade": "neutral", "note": "5年超额 +3.69%，前半段驱动"}`
- 高成长/核心资产/GARP：`{"grade": "failed", "note": "5年超额 -2.34% / -10.36% / -19.05%，回测失效"}`

报告每个预设标题旁标注 grade 与 note；`failed` 级预设默认不进定时任务（`SCREENER_SCHEDULE_PRESETS` 默认值改为 core→financial_value+deep_value）。种子重灌脚本幂等更新。

## Constraints

- 不 drop 表、不做删列迁移；「删类留表」模式延续
- ruff 只跑改动文件；pytest 与冒烟严格串行；冒烟前核对 alembic head
- 零新增 LLM/akshare 真实调用；fact_checks 新逻辑纯函数可测
- 提交切分：E1/E2/E3/A1/A2/A3/A4 各自或就近合并提交；提交信息先过目；不自行 push
- 测试豁免清单以 `memory/ai-research-os-session.md` 最新条目为准

## 验收标准

1. grep `ask\|/llm/models` 在 knowledge/ 零命中；`llm_usage\|adapters/llm` 零命中（embedding 除外）
2. grep `news_service` 零命中；前端路由 4 条（/screener /market /documents /system）
3. 金融价值预设冒烟：券商候选不再集体 insufficient（exempt 或 pass）
4. 报告尾部出现轮次对比段；推荐表无置信度列；预设标题带证据等级
5. 全量 pytest 除豁免清单外全绿；单轮冒烟 ≤2 分钟
6. 整分支评审通过

## 待定项（后续轮次）

1. valuation_history 喂数据（akshare 换源重试）→ 估值分位数化的前置
2. 死表 drop 迁移（research/portfolio/ai schema 等）——一次性清理，需单独拍板
3. profile_service 价值重估（9KB 服务 + akshare 调用面换一个「公司简介」）
