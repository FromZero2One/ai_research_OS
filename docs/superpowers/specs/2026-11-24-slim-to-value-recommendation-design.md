# 价值推荐聚焦 · 二次瘦身设计（2026-11-24）

## 意图与理由

用户的真实诉求只有一句话：**系统通过各种数据，给出具备价值投资价值的股票，并给出原因。**

2026-11-24 第一次瘦身删掉了 research/portfolio/ai/dashboard 四个模块。本次是第二次瘦身：把 screener 内部长出来的枝叶（组合、表现跟踪、freeform 模式、交互式回测 UI 等）砍掉，把腾出的注意力集中在两件事上：

1. **推荐质量**：事实检查确定性化，让深度价值预设复活。
2. **交付形态**：产出物收敛为一份 Markdown「投资理由文档」，每日定时自动生成，可选 Webhook 推送。

交互式回测降级为脚本命令（保留 `backtest*.py` 核心引擎与 `tools/run_backtest_queue.py`，删除回测路由/模型前端面板）——理由：显著性检验还没做，常看回测面板会诱导过度调参；脚本按需跑一次足够。

## 目标 / 非目标 / 反目标

- **目标**：每日自动产出一份 Markdown 推荐清单（股票 + 买入理由逐条引用 + 数据不足提示）；深度价值预设可产出非零推荐；删除全部资金管理/表现跟踪代码。
- **非目标**：不做统计显著性检验（后续独立课题）；不做仓位建议；不动 Market/Document/Knowledge 数据管道；不改数据库 schema（表保留，同第一次瘦身惯例）。
- **反目标**：禁止把「推荐后表现」伪装成校准依据重新加回来；禁止 LLM 参与任何数字判定。

## 砍除清单（代码删除，DB 表保留）

### screener 模块
| 删除 | 文件/位置 |
|---|---|
| 组合构建+再平衡 | `portfolio.py`, `portfolio_store.py`, `rebalance.py`, `routes/portfolio.py`, `portfolios`/`performance_snapshots` 模型注册处删除 |
| 表现跟踪+快照 | `performance.py`, `performance_service.py`, `performance_store.py`, `routes/performance.py`, `core/performance_schedule.py` + 对应调度任务注册 |
| 回测交互层 | `routes/backtest.py`（保留 `backtest*.py` 引擎与 `backtest_service.py` 中的 `run_backtest_by_id` 供脚本调用；`backtest_runs` 表保留） |
| freeform 模式 | `translate.py`, `criteria.py`, `routes/criteria.py`, `screener/criteria.md`；`service.py` 中 `params is None` 分支 + **`service.py:429` 的 translate 回路改直连**（`compose_rules` 输出直接喂给 screening/judge，不经 LLM 翻译）；注：`screener_rules` 表在当前 models.py 中已不存在，无需删模型（评审核实） |
| 用户自建预设 | `presets.py` 中 create/update/delete（保留 list/read）；`routes/presets.py` 相应路由收缩为只读；`PresetManager.vue` 删除 |
| CSV 导出 | `routes/runs.py` 的 `/export` |
| 运行取消 | `cancel.py` + 完整清扫：`errors.py` 的 `ScreenerCancelled`、`service.py` cancel 导入/检查（21, 79-91, 390-399）、`judge.py:471-497`（`should_stop`）、`routes/runs.py` `/cancel`、`reset_stuck_runs.py` SQL 中的 `cancelled`、前端 `useCancelScreenerRun` + `Screener.vue` 的 cancelling 状态；`models.py:27` CHECK 中移除 `'cancelling'`（ORM 层即可，库内旧数据不受影响，无需迁移）；`ACTIVE_STATUSES`（service.py:79）与 `core/screener_schedule.py:18` `_ACTIVE` 同步收窄 |
| 近似命中 | `screening.evaluate_near_misses*` 及报告分区。**附带修复一个潜伏 bug**：`service.py:514` 从 `screener.compose` 导入不存在的 `evaluate_near_misses_by_preset`（union+定性路径一旦走到会 ImportError，测试从未覆盖）——删除该分支即顺带消除 |
| Webhook | 删除 `notify.py` 中失败告警与变化日报推送？**否——保留**（交付形态之一，见下） |

### 前端
| 删除 | 理由 |
|---|---|
| `Screener.vue` 中组合/表现/回测/CSV/取消/日报按钮及面板 | 对应后端已删 |
| `PresetManager.vue` + 预设抽屉 | 预设只读 |
| `Knowledge.vue` 页面 + 路由 | 知识检索已由深判内部消费，无需独立 UI |
| `ReportCharts.vue` | 死代码（研究模块遗留） |
| `api.ts` 中对应 hooks | — |

`Screener.vue` 目标 ~400 行以内：触发（预设多选）、运行状态、**报告渲染（首页即清单）**。

### core/
- 删除 `performance_schedule.py` 与 scheduler 中 `performance_snapshot` 任务。
- 保留 `screener_schedule`（每日产出交付物的引擎）与 `market_data_update`、`financial_data_update`、`event_log_cleanup`。

## 保留清单

- Webhook 通知：`notify.py` 保留，`SCREENER_WEBHOOK_NOTIFY_ON` 默认 `changes`。交付形态 = **Markdown 文档为主，Webhook 可选**。
- 回测脚本化：`tools/run_backtest_queue.py` 保留并适配（经 `backtest_service.run_backtest_by_id` 直调，绕过已删的路由）；结果照旧写 `screener/reports/`。
- 事件日志、任务队列、调度器、数据质量卡片（`/screener/data-quality` 保留，判断「今天这份清单可不可信」需要它）。
- 运行 diff（`diff.py`/`diff_service.py`）：保留——变化日报（新推荐/掉出）是「价值清单」的核心增量信息，落到 md 里。

## 强化清单（本次的新功能点）

### 1. 事实检查确定性化（新文件 `screener/fact_checks.py`）

把三类事实性定性标准从 LLM prompt 中移出，改为确定性判定，每个预设的 qualitative 条目新增机器可执行形态：

| 检查项 | 实现方式 | 输出示例 |
|---|---|---|
| 审计意见 | KB 检索「审计报告/保留意见/无保留」段落 + 关键词判定（非 LLM） | `审计意见: 无保留 [3]` / `未找到审计段落 → insufficient` |
| 诉讼/处罚 | KB 检索「诉讼/仲裁/处罚/立案」+ 命中即 fail | `未发现重大诉讼处罚 [7]` |
| 现金覆盖 | 财务指标确定性计算（operating_cash_flow / 有息负债等，复用 `valuation.py` 派生） | `现金覆盖 1.8x（阈值 1.0）` |

实现要点：
- `seeds.py` 内置预设的 qualitative 条目改写为结构化对象 `{type: fact_check, check: audit_opinion|litigation|cash_coverage, threshold?, text?}`（向后兼容：纯字符串条目仍走 LLM）。**compose.py 需先行拆分**：`compose_rules` 目前对 qualitative 做字符串拼接/去重（`compose.py:58-63`），dict 条目会崩——结构化条目拆到独立 `fact_checks` 键，叙事字符串保持原路径，`judge_candidates` 的 `qualitative: list[str]` 签名不变。
- 结构化预设改写后通过一次性小脚本调用 `insert_builtin_seeds` 幂等重灌（不走假迁移）。
- 判定结果直接进入 `criteria_hits`，verdict 规则：事实检查任一 fail → reject；任一「未找到证据」→ insufficient；全部 pass + LLM 叙事标准 pass → recommend。
- **LLM 职责收窄为**：仅判断叙事类标准（行业景气、竞争地位、护城河），逐条检索+引用规则不变。

### 2. 报告改造为「投资理由文档」（改 `report.py`）

每只推荐股固定四段，顺序即重要度：

```markdown
### 1. 杭州银行 (600926) — 推荐 (置信 0.92, 排序 #1)

**量化筛选**（6/6 规则通过）
- PB 0.82 < 1.5 ✅（行业内分位 23%）
- ROE 11.2% > 8 ✅ ...

**事实检查**
- 审计意见: 无保留意见 [3] ✅
- 诉讼/处罚: 未发现 [7] ✅
- 现金覆盖: 1.8x > 1.0 ✅

**年报证据（LLM 判定的叙事标准）**
- 资产质量优异：不良率 0.76%，低于同业均值 [1][5]
- ...

**不推荐/存疑原因**
- （无）或：营收增速连续两期放缓 [12]
```

同时保留：概览（数据时效、股票池卫生统计）、变化日报区（对比上轮）、数据不足名单。

### 3. 交付链路

- 每日 16:30 定时任务照旧触发 → 报告落 `screener/reports/YYYY-MM-DD-<runid>.md`（现有路径不变）。
- **固定最新报告指针**：`GET /screener/latest-report` 返回最近 completed run 的 markdown 文本；前端首页直接渲染。
- 可选 Webhook 推送报告摘要（已有能力，不动）。

## 约束

- 不做 alembic 迁移（不 drop 表）；模型文件里移除对应 ORM 类即可（表留在库里）。
- 测试同步收缩：删除组合/表现/回测API/translate/criteria 相关用例（约 25 个文件），新增 `test_fact_checks.py` 与报告新格式用例。
- 全程不 push；改动文件跑 ruff + pre-commit。
- 预设改写后需重跑 `insert_builtin_seeds`（迁移与测试 conftest 共用事实源）。

## 留给实现者裁量

- `fact_checks.py` 的检索复用 `judge._retrieve_per_criterion` 还是走轻量路径（top_k=1 无并发）——按性能实测定。
- Screener.vue 收缩后的具体布局（建议：顶部触发条 → 数据质量卡 → 报告主体）。
- 前端报告渲染沿用 marked + DOMPurify。
- 前端删除需连带清理：`router/index.ts` 的 knowledge 路由、`Sidebar.vue` 菜单项、`api.ts` 中 `searchKnowledge`/`useAskKnowledge`/`useCancelScreenerRun`/组合/表现相关 hooks。
- `core/performance_schedule.py` 删除时同步清掉 `api/app.py` 的导入与 `scheduler.py` 的任务注册。
