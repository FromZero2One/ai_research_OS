# 设计文档：LLM 智能选股器（Screener）

- 日期：2026-10-21
- 状态：已确认（对话中分节确认）
- 前置：跨会话证据继承（2026-10-16，迁移 head `a9c4d7e2f1b8`）

## 目标

用户用一份可随时修改的自然语言选股标准文档（markdown），手动触发一次筛选流程，产出一份 Markdown 选股报告（推荐股票 + 入选理由 + 关键指标 + 标准吻合度说明）。LLM 负责"理解标准"和"定性深判"，筛选执行是确定性的。

## 明确的决策（对话确认）

| 决策点 | 结论 |
|---|---|
| 判断标准 | 用户维护 markdown 文档，随时可改；LLM 理解并翻译成可执行规则 |
| 股票池 | 可配置：全部 A 股 / 沪深主板 / 创业板 / 科创板 / 自选公司列表；标准文档内可覆盖 |
| LLM 角色 | 两层：①翻译标准为结构化规则（缓存） ②对初筛通过股票逐只定性深判 |
| 筛选执行 | 确定性（数据库查询/指标计算），不逐只调 LLM 做初筛 |
| 推送形式 | Markdown 报告，落本地目录 + 系统内可查看 |
| 报告内容 | 推荐列表 + 每只入选理由 + 关键指标快照 + 标准吻合度说明（逐条对照标准文档） |
| 触发方式 | 仅手动触发（后端端点 + 前端按钮） |
| 模拟盘 | 明确排除（用户手动操作），不在本设计范围 |
| 回测 | 明确排除，但深判结果落库以便后续回测/追溯 |
| 市场 | 第一版仅 A 股（akshare 链路最成熟），港美股留扩展点 |

## 架构

新建后端 `screener/` 模块（复用 core 的 LLM 适配器、DI 容器、事件日志、任务系统），前端新增一个"智能选股"页面。

### 1. 标准文档

- 位置：`screener/criteria.md`（仓库内，用户直接编辑）
- 内容：自然语言选股标准（量化阈值 + 定性条件）+ 可选的股票池范围声明
- 文档 hash 缓存：标准翻译结果存 `ai.prompt_templates` 不合适，新建 `screener.screener_rules` 表（`doc_hash`、`rules` JSONB、`criteria_text`、`created_at`），hash 未变则跳过翻译

### 2. 流水线（4 步）

```
①translate  LLM: criteria.md → 结构化规则 JSON
②screen     确定性初筛：全市场快照 + 财务指标，跑规则 → 候选（预计几十~几百只）
③judge      LLM 逐只定性深判候选（可检索知识库/新闻），输出 推荐/不推荐 + 理由 + 置信度
④report     生成 Markdown 报告：推荐列表 + 指标快照 + 标准吻合度说明
```

- **①翻译**：复用 `core/adapters/llm.py`；规则 schema 用 JSON Schema 约束输出（指标键对齐 `market.financial_metrics` 枚举 + `market.ratio_service` 比率键 + 行情快照字段）；翻译失败重试 1 次
- **②初筛**：第一步做股票池过滤（股票池声明由标准文档解析进规则 JSON，作为规则的一部分；按 ticker 前缀映射板块：60/00 主板、30 创业板、68 科创板；自选池取 PG `is_active` 公司 ∪ 文档内列出的 ticker，文档声明优先）；第二步跑量化规则 — 全市场实时快照用 akshare `stock_zh_a_spot_em`（子进程直连，复用 `market/akshare_executor.py` 模式，akshare 失败则本次运行报错终止）；财务指标复用 `FinancialService`（PG 缓存优先，规则只对 PG 已有财务数据的公司做财务条件过滤，无数据的公司按规则声明的 missing_data_policy 决定放行/排除，默认排除）
- **③深判**：每只候选组装上下文（行情快照 + 财务比率 + 可选知识库检索 top 片段 + 近期新闻（有则带上，无则静默省略）），LLM 输出结构化 JSON（recommend: bool、reasons: list、criteria_hits: list、confidence: float）；候选数量上限可配置（默认 50，超出按初筛得分截断，得分 = 命中条件数/适用条件数，同分按市值排序）；**单只深判失败不导致整次运行失败**，该只标记 failed 继续
- **④报告**：报告文件落 `screener/reports/YYYY-MM-DD-<run_id>.md`；同时存 `screener.screener_runs` 表

### 3. 数据模型（新 schema `screener`）

```python
ScreenerRun        # 一次筛选：status(pending/screening/judging/completed/failed)、
                   # criteria_hash、rules(JSONB)、candidate_count、result_count、
                   # report_path、error、started/finished_at
ScreenerJudgement  # 每只候选的深判结果：run_id FK、ticker、name、recommend、
                   # reasons(JSONB)、criteria_hits(JSONB)、confidence、
                   # snapshot(JSONB：行情+指标快照)、created_at
ScreenerRule       # 标准翻译缓存：doc_hash unique、rules(JSONB)、criteria_text
```

迁移：alembic revision，基于 head `a9c4d7e2f1b8`。

### 4. API（`/screener`）

- `POST /screener/runs` — 触发筛选（持久后台任务，复用 `core/task_manager`，任务类型 `screener_run`；同一时间只允许一个 running/pending）
- `GET /screener/runs` — 历史运行列表
- `GET /screener/runs/{id}` — 运行详情 + 深判结果列表
- `GET /screener/runs/{id}/report` — 报告 markdown 原文
- `GET /screener/criteria` / `PUT /screener/criteria` — 读取/更新标准文档（前端可编辑，落回 `screener/criteria.md`）
- `GET /screener/rules` — 当前缓存的结构化规则（便于人工核对 LLM 理解是否正确）

### 5. 前端（新增"智能选股"页面 `/screener`）

- 标准文档编辑器（textarea/markdown，保存即更新文档并使规则缓存失效）
- "开始筛选"按钮 + 运行进度（轮询 run 状态）
- 最新报告渲染（marked + DOMPurify，与 Knowledge.vue 同模式）
- 历史运行列表 + 每次运行的推荐股票表（含理由、置信度、吻合度）

### 6. 报告结构（Markdown）

```markdown
# 智能选股报告 YYYY-MM-DD
## 概览（股票池、候选数、推荐数、耗时）
## 推荐列表
| 代码 | 名称 | 现价 | 关键指标 | 置信度 |
### 每只入选理由（criteria_hits 逐条）
## 标准吻合度说明（对照标准文档逐条：命中/未命中/数据缺失）
## 附：候选但未推荐（原因摘要）
```

## 非目标（Non-goals）

- 模拟盘 / 自动下单
- 回测引擎（但深判结果落库，为将来回测留数据）
- 定时自动触发（仅手动）
- 港美股支持
- 全市场财务数据自动补齐（采集全市场财务会非常慢；第一版财务条件依赖 PG 已有数据）

## 留给实现者的决定

- 深判的 LLM prompt 具体措辞与 few-shot 设计
- 初筛得分排序规则（候选超上限时如何截断）
- 报告中"标准吻合度说明"的排版细节
- 规则 JSON 的具体字段命名（对齐现有 metric 枚举即可）
- 知识库检索是否接入第一版深判上下文（建议接，复用 KnowledgeService.search）
